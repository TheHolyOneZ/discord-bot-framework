import os
import json
import asyncio
import aiofiles
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
import hashlib
from collections import OrderedDict
import logging
logger = logging.getLogger('discord')

class AtomicFileHandler:
    def __init__(self, cache_ttl: int = 300, max_cache_size: int = 1000):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._locks: Dict[str, asyncio.Lock] = {}
        self._cache_ttl = cache_ttl
        self._max_cache_size = max_cache_size
        self._lock_cleanup_threshold = 500
    
    def _get_lock(self, filepath: str) -> asyncio.Lock:
        if filepath not in self._locks:
            self._locks[filepath] = asyncio.Lock()
            
            if len(self._locks) > self._lock_cleanup_threshold:
                self._cleanup_locks()
        return self._locks[filepath]
    
    
    
    def _cleanup_locks(self):
        current_time = datetime.now().timestamp()
        inactive_threshold = 300
        
        
        locks_to_remove = []
        for fp, lock in list(self._locks.items()):
            if not lock.locked():
                cache_key = self._get_cache_key(fp)
                if cache_key in self._cache:
                    _, timestamp = self._cache[cache_key]
                    if (current_time - timestamp) > inactive_threshold:
                        locks_to_remove.append(fp)
                else:
                    locks_to_remove.append(fp)
        
        for fp in locks_to_remove:
            del self._locks[fp]
        
        logger.debug(f"Cleaned up {len(locks_to_remove)} inactive locks")
    
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
        
        if cache_key in self._cache:
            del self._cache[cache_key]
        
        self._cache[cache_key] = (data, datetime.now().timestamp())
        self._cache.move_to_end(cache_key)
        
        while len(self._cache) > self._max_cache_size:
            self._cache.popitem(last=False)
    
    def _get_cache(self, filepath: str) -> Optional[Any]:
        if self._is_cache_valid(filepath):
            cache_key = self._get_cache_key(filepath)
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key][0]
        return None
    
    def invalidate_cache(self, filepath: str):
        cache_key = self._get_cache_key(filepath)
        if cache_key in self._cache:
            del self._cache[cache_key]
    
    def get_cache_stats(self) -> Dict[str, int]:
        return {
            "size": len(self._cache),
            "max_size": self._max_cache_size,
            "locks": len(self._locks)
        }
    
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
                "base_path": "./data"
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
            "command_permissions": {},
            "slash_limiter": {
                "max_limit": 100,
                "warning_threshold": 90,
                "safe_limit": 95
            },
            "framework": {
                "load_cogs": True
            }
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
    def __init__(self, base_path: str = "./data", file_handler: Optional[AtomicFileHandler] = None):
        self.base_path = Path(base_path)
        self.file_handler = file_handler or AtomicFileHandler()
        self._guild_connections: Dict[int, Any] = {}
        self._connection_locks: Dict[int, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_path / "main.db"
        self.conn = None
    
    async def _get_guild_db_path(self, guild_id: int) -> Path:
        guild_folder = self.base_path / str(guild_id)
        guild_folder.mkdir(parents=True, exist_ok=True)
        return guild_folder / "guild.db"
    
    async def _create_tables(self, conn):
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS command_stats (
                command_name TEXT PRIMARY KEY,
                usage_count INTEGER DEFAULT 0,
                last_used TIMESTAMP
            )
        """)
        
        await conn.commit()
    
    async def connect(self):
        import aiosqlite
        if not self.conn:
            self.conn = await aiosqlite.connect(str(self.db_path))
            self.conn.row_factory = aiosqlite.Row
            await self.conn.execute("PRAGMA journal_mode=WAL")
            await self.conn.execute("PRAGMA synchronous=NORMAL")
            await self._create_main_tables()

    async def _create_main_tables(self):
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS global_stats (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.conn.commit()
    
    async def _get_guild_connection(self, guild_id: int):
        import aiosqlite
        
        if guild_id not in self._connection_locks:
            async with self._global_lock:
                if guild_id not in self._connection_locks:
                    self._connection_locks[guild_id] = asyncio.Lock()
        
        async with self._connection_locks[guild_id]:
            if guild_id not in self._guild_connections:
                db_path = await self._get_guild_db_path(guild_id)
                conn = await aiosqlite.connect(str(db_path))
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await self._create_tables(conn)
                self._guild_connections[guild_id] = conn
            
            return self._guild_connections[guild_id]
    
    async def close(self):
        async with self._global_lock:
            for guild_id, conn in list(self._guild_connections.items()):
                try:
                    await conn.close()
                    logger.info(f"Closed connection for guild {guild_id}")
                except Exception as e:
                    logger.error(f"Error closing guild {guild_id} connection: {e}")
            
            self._guild_connections.clear()
            
            if self.conn:
                await self.conn.close()
                self.conn = None
            
            self._connection_locks.clear()
    
    async def backup(self, guild_id: Optional[int] = None):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if guild_id:
            db_path = await self._get_guild_db_path(guild_id)
            backup_path = db_path.parent / f"guild_backup_{timestamp}.db"
            try:
                if guild_id in self._guild_connections:
                    await self._guild_connections[guild_id].execute("PRAGMA wal_checkpoint(FULL)")
                shutil.copy2(db_path, backup_path)
                logger.info(f"Database backed up for guild {guild_id}: {backup_path}")
                return True
            except Exception as e:
                logger.error(f"Backup failed for guild {guild_id}: {e}")
                return False
        else:
            success_count = 0
            for gid in list(self._guild_connections.keys()):
                if await self.backup(gid):
                    success_count += 1
            logger.info(f"Backed up {success_count}/{len(self._guild_connections)} guild databases")
            return True
    
    async def get_guild_prefix(self, guild_id: int) -> Optional[str]:
        conn = await self._get_guild_connection(guild_id)
        
        try:
            async with conn.execute(
                "SELECT value FROM guild_settings WHERE key = 'prefix'"
            ) as cursor:
                row = await cursor.fetchone()
                return row['value'] if row else None
        except Exception as e:
            logger.error(f"Error getting prefix for guild {guild_id}: {e}")
            return None
    
    async def set_guild_prefix(self, guild_id: int, prefix: str):
        conn = await self._get_guild_connection(guild_id)
        
        try:
            await conn.execute(
                "INSERT OR REPLACE INTO guild_settings (key, value) VALUES ('prefix', ?)",
                (prefix,)
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Error setting prefix for guild {guild_id}: {e}")
    
    async def increment_command_usage(self, command_name: str):
        if not self.conn:
            return
        try:
            await self.conn.execute("""
                INSERT INTO global_stats (key, value) 
                VALUES (?, '1')
                ON CONFLICT(key) DO UPDATE SET 
                    value = CAST(CAST(value AS INTEGER) + 1 AS TEXT),
                    updated_at = CURRENT_TIMESTAMP
            """, (f"cmd_{command_name}",))
            await self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to increment command usage: {e}")
    
    async def get_command_stats(self):
        if not self.conn:
            return []
        try:
            async with self.conn.execute(
                "SELECT key, value FROM global_stats WHERE key LIKE 'cmd_%'"
            ) as cursor:
                rows = await cursor.fetchall()
                return [(row['key'].replace('cmd_', ''), int(row['value'])) for row in rows]
        except Exception:
            return []
    
    async def cleanup_guild(self, guild_id: int):
        async with self._global_lock:
            if guild_id in self._guild_connections:
                try:
                    await self._guild_connections[guild_id].close()
                    del self._guild_connections[guild_id]
                    logger.info(f"Cleaned up connection for guild {guild_id}")
                except Exception as e:
                    logger.error(f"Error cleaning up guild {guild_id}: {e}")
            
            if guild_id in self._connection_locks:
                del self._connection_locks[guild_id]

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