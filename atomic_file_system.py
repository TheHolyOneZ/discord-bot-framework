import os
import json
import asyncio
import aiofiles
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
import hashlib


class AtomicFileHandler:
    def __init__(self, cache_ttl: int = 300):
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._cache_ttl = cache_ttl
        self._write_queue: Dict[str, asyncio.Queue] = {}
    
    def _get_lock(self, filepath: str) -> asyncio.Lock:
        if filepath not in self._locks:
            self._locks[filepath] = asyncio.Lock()
        return self._locks[filepath]
    
    def _get_cache_key(self, filepath: str) -> str:
        return hashlib.md5(filepath.encode()).hexdigest()
    
    def _is_cache_valid(self, filepath: str) -> bool:
        cache_key = self._get_cache_key(filepath)
        if cache_key not in self._cache:
            return False
        _, timestamp = self._cache[cache_key]
        return (datetime.now().timestamp() - timestamp) < self._cache_ttl
    
    def _set_cache(self, filepath: str, data: Any):
        cache_key = self._get_cache_key(filepath)
        self._cache[cache_key] = (data, datetime.now().timestamp())
    
    def _get_cache(self, filepath: str) -> Optional[Any]:
        if self._is_cache_valid(filepath):
            cache_key = self._get_cache_key(filepath)
            return self._cache[cache_key][0]
        return None
    
    def invalidate_cache(self, filepath: str):
        cache_key = self._get_cache_key(filepath)
        if cache_key in self._cache:
            del self._cache[cache_key]
    
    async def atomic_read(self, filepath: str, use_cache: bool = True) -> Optional[str]:
        if use_cache:
            cached = self._get_cache(filepath)
            if cached is not None:
                return cached
        
        lock = self._get_lock(filepath)
        async with lock:
            try:
                if not os.path.exists(filepath):
                    return None
                
                async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                    content = await f.read()
                
                if use_cache:
                    self._set_cache(filepath, content)
                
                return content
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
                return None
    
    async def atomic_write(self, filepath: str, content: str, invalidate_cache_after: bool = True):
        lock = self._get_lock(filepath)
        async with lock:
            try:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=os.path.dirname(filepath),
                    prefix='.tmp_',
                    suffix=os.path.basename(filepath)
                )
                
                try:
                    async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                        await f.write(content)
                    
                    os.close(temp_fd)
                    
                    if os.name == 'nt':
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    
                    shutil.move(temp_path, filepath)
                    
                    if invalidate_cache_after:
                        self.invalidate_cache(filepath)
                    else:
                        self._set_cache(filepath, content)
                    
                    return True
                except Exception as e:
                    os.close(temp_fd)
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    raise e
            except Exception as e:
                print(f"Error writing to {filepath}: {e}")
                return False
    
    async def atomic_read_json(self, filepath: str, use_cache: bool = True) -> Optional[Dict]:
        content = await self.atomic_read(filepath, use_cache)
        if content is None:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"JSON decode error in {filepath}: {e}")
            return None
    
    async def atomic_write_json(self, filepath: str, data: Dict, invalidate_cache_after: bool = True) -> bool:
        try:
            content = json.dumps(data, indent=4)
            return await self.atomic_write(filepath, content, invalidate_cache_after)
        except Exception as e:
            print(f"Error serializing JSON for {filepath}: {e}")
            return False


class SafeConfig:
    def __init__(self, config_path: str = "./config.json", file_handler: Optional[AtomicFileHandler] = None):
        self.config_path = config_path
        self.file_handler = file_handler or AtomicFileHandler()
        self.data = {}
        self._initialized = False
    
    async def initialize(self):
        if self._initialized:
            return
        self.data = await self._load_config()
        self._initialized = True
    
    async def _load_config(self) -> dict:
        config = await self.file_handler.atomic_read_json(self.config_path)
        
        if config:
            return config
        
        default_config = {
            "prefix": "!",
            "owner_ids": [],
            "auto_reload": True,
            "status": {
                "type": "watching",
                "text": "{guilds} servers"
            },
            "database": {
                "path": "./data/bot.db"
            },
            "logging": {
                "level": "INFO",
                "max_bytes": 10485760,
                "backup_count": 5
            },
            "extensions": {
                "auto_load": True,
                "blacklist": []
            },
            "cooldowns": {
                "default_rate": 3,
                "default_per": 5.0
            },
            "command_permissions": {}
        }
        
        await self.save(default_config)
        return default_config
    
    async def save(self, data: dict = None):
        if data:
            self.data = data
        await self.file_handler.atomic_write_json(self.config_path, self.data)
    
    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self.data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value
    
    async def set(self, key: str, value: Any):
        keys = key.split('.')
        data = self.data
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        data[keys[-1]] = value
        await self.save()


class SafeDatabaseManager:
    def __init__(self, db_path: str, file_handler: Optional[AtomicFileHandler] = None):
        self.db_path = db_path
        self.file_handler = file_handler or AtomicFileHandler()
        self.conn: Optional[Any] = None
        self._db_lock = asyncio.Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    async def connect(self):
        import aiosqlite
        
        async with self._db_lock:
            if self.conn is None:
                self.conn = await aiosqlite.connect(self.db_path)
                self.conn.row_factory = aiosqlite.Row
                await self.conn.execute("PRAGMA journal_mode=WAL")
                await self.conn.execute("PRAGMA synchronous=NORMAL")
                await self.conn.execute("PRAGMA cache_size=-64000")
                await self._create_tables()
    
    async def _create_tables(self):
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT,
                settings TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_data (
                user_id INTEGER PRIMARY KEY,
                data TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS command_stats (
                command_name TEXT PRIMARY KEY,
                usage_count INTEGER DEFAULT 0,
                last_used TIMESTAMP
            )
        """)
        
        await self.conn.commit()
    
    async def close(self):
        async with self._db_lock:
            if self.conn:
                await self.conn.close()
                self.conn = None
    
    async def backup(self, backup_path: Optional[str] = None):
        if backup_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self.db_path}.backup_{timestamp}"
        
        async with self._db_lock:
            try:
                shutil.copy2(self.db_path, backup_path)
                print(f"Database backed up to: {backup_path}")
                return True
            except Exception as e:
                print(f"Backup failed: {e}")
                return False
    
    async def get_guild_prefix(self, guild_id: int) -> Optional[str]:
        async with self.conn.execute(
            "SELECT prefix FROM guild_settings WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row['prefix'] if row else None
    
    async def set_guild_prefix(self, guild_id: int, prefix: str):
        await self.conn.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, prefix) VALUES (?, ?)",
            (guild_id, prefix)
        )
        await self.conn.commit()
    
    async def increment_command_usage(self, command_name: str):
        await self.conn.execute(
            """INSERT INTO command_stats (command_name, usage_count, last_used)
               VALUES (?, 1, CURRENT_TIMESTAMP)
               ON CONFLICT(command_name) DO UPDATE SET
               usage_count = usage_count + 1,
               last_used = CURRENT_TIMESTAMP""",
            (command_name,)
        )
        await self.conn.commit()
    
    async def get_command_stats(self):
        async with self.conn.execute(
            "SELECT command_name, usage_count FROM command_stats ORDER BY usage_count DESC"
        ) as cursor:
            return await cursor.fetchall()


class SafeLogRotator:
    def __init__(self, log_dir: str = "./botlogs", max_size: int = 10485760, backup_count: int = 5):
        self.log_dir = Path(log_dir)
        self.max_size = max_size
        self.backup_count = backup_count
        self.log_dir.mkdir(exist_ok=True)
        self._rotation_lock = asyncio.Lock()
    
    async def should_rotate(self, log_file: Path) -> bool:
        if not log_file.exists():
            return False
        return log_file.stat().st_size >= self.max_size
    
    async def rotate_log(self, log_file: Path):
        async with self._rotation_lock:
            if not await self.should_rotate(log_file):
                return
            
            for i in range(self.backup_count - 1, 0, -1):
                old_backup = log_file.with_suffix(f"{log_file.suffix}.{i}")
                new_backup = log_file.with_suffix(f"{log_file.suffix}.{i+1}")
                
                if old_backup.exists():
                    if new_backup.exists():
                        new_backup.unlink()
                    old_backup.rename(new_backup)
            
            first_backup = log_file.with_suffix(f"{log_file.suffix}.1")
            if first_backup.exists():
                first_backup.unlink()
            
            if log_file.exists():
                shutil.copy2(log_file, first_backup)
                log_file.unlink()
                log_file.touch()
    
    async def cleanup_old_logs(self, days: int = 30):
        cutoff = datetime.now() - timedelta(days=days)
        
        for log_file in self.log_dir.glob("*.log*"):
            if log_file.stat().st_mtime < cutoff.timestamp():
                try:
                    log_file.unlink()
                    print(f"Removed old log: {log_file.name}")
                except Exception as e:
                    print(f"Failed to remove {log_file.name}: {e}")


global_file_handler = AtomicFileHandler(cache_ttl=300)
global_log_rotator = SafeLogRotator()