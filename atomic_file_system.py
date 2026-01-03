"""
Atomic File System
Thread-safe file operations with LRU caching, atomic writes, and diagnostics
Provides enterprise-grade file handling for the Discord bot framework
"""

import os
import json
import asyncio
import aiofiles
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timedelta
import hashlib
from collections import OrderedDict
import logging
import time
import traceback
from discord.ext import commands, tasks
import discord

logger = logging.getLogger('discord')


class AtomicFileHandler:
    """
    Thread-safe atomic file handler with LRU caching
    Prevents data corruption through tempfile-based atomic writes
    """
    
    def __init__(self, cache_ttl: int = 300, max_cache_size: int = 1000):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._locks: Dict[str, tuple[asyncio.Lock, float]] = {}
        self._cache_ttl = cache_ttl
        self._max_cache_size = max_cache_size
        self._lock_cleanup_threshold = 500
        self._write_retry_attempts = 3
        self._write_retry_delay = 0.1
        
        self.metrics = {
            "reads": 0,
            "writes": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_bypasses": 0,
            "write_failures": 0,
            "read_failures": 0,
            "lock_cleanups": 0,
            "cache_invalidations": 0
        }
        
        logger.info("Atomic File Handler: Initialized with cache_ttl=%ds, max_cache=%d", cache_ttl, max_cache_size)
    
    def _get_lock(self, filepath: str) -> asyncio.Lock:
        """Get or create lock for filepath with timestamp tracking"""
        if filepath not in self._locks:
            self._locks[filepath] = (asyncio.Lock(), time.time())
            
            if len(self._locks) > self._lock_cleanup_threshold:
                self._cleanup_locks()
        
        lock, _ = self._locks[filepath]
        return lock
    
    def _cleanup_locks(self):
        """Remove inactive locks that haven't been used recently"""
        current_time = time.time()
        inactive_threshold = 300
        
        locks_to_remove = []
        for fp, (lock, created_time) in list(self._locks.items()):
            if not lock.locked():
                cache_key = self._get_cache_key(fp)
                if cache_key in self._cache:
                    _, cache_timestamp = self._cache[cache_key]
                    if (current_time - cache_timestamp) > inactive_threshold:
                        locks_to_remove.append(fp)
                elif (current_time - created_time) > inactive_threshold:
                    locks_to_remove.append(fp)
        
        for fp in locks_to_remove:
            del self._locks[fp]
        
        self.metrics["lock_cleanups"] += 1
        logger.debug(f"Atomic File Handler: Cleaned up {len(locks_to_remove)} inactive locks")
    
    def _get_cache_key(self, filepath: str) -> str:
        """Generate cache key from filepath"""
        return hashlib.md5(filepath.encode()).hexdigest()
    
    def _is_cache_valid(self, filepath: str) -> bool:
        """Check if cached data is still valid"""
        cache_key = self._get_cache_key(filepath)
        if cache_key not in self._cache:
            return False
        _, timestamp = self._cache[cache_key]
        return (time.time() - timestamp) < self._cache_ttl
    
    def _set_cache(self, filepath: str, data: Any):
        """Store data in LRU cache"""
        cache_key = self._get_cache_key(filepath)
        
        if cache_key in self._cache:
            del self._cache[cache_key]
        
        self._cache[cache_key] = (data, time.time())
        self._cache.move_to_end(cache_key)
        
        while len(self._cache) > self._max_cache_size:
            self._cache.popitem(last=False)
    
    def _get_cache(self, filepath: str) -> Optional[Any]:
        """Retrieve data from cache if valid"""
        if self._is_cache_valid(filepath):
            cache_key = self._get_cache_key(filepath)
            self._cache.move_to_end(cache_key)
            self.metrics["cache_hits"] += 1
            return self._cache[cache_key][0]
        
        self.metrics["cache_misses"] += 1
        return None
    
    def invalidate_cache(self, filepath: str):
        """Manually invalidate cache entry"""
        cache_key = self._get_cache_key(filepath)
        if cache_key in self._cache:
            del self._cache[cache_key]
            self.metrics["cache_invalidations"] += 1
            logger.debug(f"Atomic File Handler: Cache invalidated for {filepath}")
    
    def clear_all_cache(self):
        """Clear entire cache"""
        count = len(self._cache)
        self._cache.clear()
        self.metrics["cache_invalidations"] += count
        logger.info(f"Atomic File Handler: Cleared all cache ({count} entries)")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        total_requests = self.metrics["cache_hits"] + self.metrics["cache_misses"]
        hit_rate = (self.metrics["cache_hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "cache_size": len(self._cache),
            "max_cache_size": self._max_cache_size,
            "cache_ttl": self._cache_ttl,
            "active_locks": len(self._locks),
            "cache_hits": self.metrics["cache_hits"],
            "cache_misses": self.metrics["cache_misses"],
            "cache_bypasses": self.metrics["cache_bypasses"],
            "hit_rate": round(hit_rate, 2),
            "total_reads": self.metrics["reads"],
            "total_writes": self.metrics["writes"],
            "write_failures": self.metrics["write_failures"],
            "read_failures": self.metrics["read_failures"],
            "lock_cleanups": self.metrics["lock_cleanups"],
            "cache_invalidations": self.metrics["cache_invalidations"]
        }
    
    def get_lock_details(self) -> Dict[str, Any]:
        """
        Get detailed information about all file locks
        Returns lock details for Live Monitor dashboard
        """
        current_time = time.time()
        locks_list = []
        active_count = 0
        
        for filepath, (lock, created_time) in self._locks.items():
            is_locked = lock.locked()
            if is_locked:
                active_count += 1
            
            # Determine last operation
            cache_key = self._get_cache_key(filepath)
            last_operation = "idle"
            last_used_time = created_time
            
            if cache_key in self._cache:
                _, cache_timestamp = self._cache[cache_key]
                last_used_time = cache_timestamp
                # If cache exists and is recent, it was likely a read
                if (current_time - cache_timestamp) < 60:
                    last_operation = "read"
                else:
                    last_operation = "idle"
            
            # If lock is currently held, it's actively writing
            if is_locked:
                last_operation = "write"
            
            locks_list.append({
                "path": filepath,
                "locked": is_locked,
                "last_operation": last_operation,
                "last_used": datetime.fromtimestamp(last_used_time).isoformat(),
                "created_at": datetime.fromtimestamp(created_time).isoformat()
            })
        
        # Sort by last_used (most recent first)
        locks_list.sort(key=lambda x: x["last_used"], reverse=True)
        
        return {
            "total_locks": len(self._locks),
            "active_locks": active_count,
            "locks": locks_list
        }
    
    async def atomic_read(self, filepath: str, use_cache: bool = True) -> Optional[str]:
        """
        Atomically read file with optional caching
        
        Args:
            filepath: Path to file
            use_cache: Whether to use cache
            
        Returns:
            File contents or None if not found
        """
        if use_cache:
            cached = self._get_cache(filepath)
            if cached is not None:
                return cached
        else:
            # Track cache bypasses
            self.metrics["cache_bypasses"] += 1
        
        lock = self._get_lock(filepath)
        async with lock:
            try:
                if not os.path.exists(filepath):
                    return None
                
                async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                    content = await f.read()
                
                self.metrics["reads"] += 1
                
                if use_cache:
                    self._set_cache(filepath, content)
                
                return content
                
            except FileNotFoundError:
                logger.debug(f"Atomic File Handler: File not found: {filepath}")
                return None
            except PermissionError as e:
                self.metrics["read_failures"] += 1
                logger.error(f"Atomic File Handler: Permission denied reading {filepath}: {e}")
                return None
            except Exception as e:
                self.metrics["read_failures"] += 1
                logger.error(f"Atomic File Handler: Error reading {filepath}: {e}")
                return None
    
    async def atomic_write(self, filepath: str, content: str, invalidate_cache_after: bool = True) -> bool:
        """
        Atomically write file with retry logic
        
        Args:
            filepath: Path to file
            content: Content to write
            invalidate_cache_after: Whether to invalidate cache after write
            
        Returns:
            True if successful, False otherwise
        """
        lock = self._get_lock(filepath)
        async with lock:
            for attempt in range(self._write_retry_attempts):
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
                        
                        self.metrics["writes"] += 1
                        return True
                        
                    except Exception as e:
                        os.close(temp_fd)
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        raise e
                        
                except PermissionError as e:
                    if attempt < self._write_retry_attempts - 1:
                        logger.warning(f"Atomic File Handler: Write attempt {attempt + 1} failed (permission): {filepath}, retrying...")
                        await asyncio.sleep(self._write_retry_delay * (attempt + 1))
                        continue
                    else:
                        self.metrics["write_failures"] += 1
                        logger.error(f"Atomic File Handler: Permission denied writing {filepath} after {self._write_retry_attempts} attempts: {e}")
                        return False
                        
                except OSError as e:
                    if attempt < self._write_retry_attempts - 1:
                        logger.warning(f"Atomic File Handler: Write attempt {attempt + 1} failed (OS error): {filepath}, retrying...")
                        await asyncio.sleep(self._write_retry_delay * (attempt + 1))
                        continue
                    else:
                        self.metrics["write_failures"] += 1
                        logger.error(f"Atomic File Handler: OS error writing {filepath} after {self._write_retry_attempts} attempts: {e}")
                        return False
                        
                except Exception as e:
                    self.metrics["write_failures"] += 1
                    logger.error(f"Atomic File Handler: Unexpected error writing {filepath}: {e}")
                    logger.debug(traceback.format_exc())
                    return False
            
            return False
    
    async def atomic_read_json(self, filepath: str, use_cache: bool = True) -> Optional[Dict]:
        """Read and parse JSON file atomically"""
        content = await self.atomic_read(filepath, use_cache)
        if content is None:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Atomic File Handler: JSON decode error in {filepath}: {e}")
            return None
    
    async def atomic_write_json(self, filepath: str, data: Dict, invalidate_cache_after: bool = True) -> bool:
        """Write data as JSON file atomically"""
        try:
            content = json.dumps(data, indent=4)
            return await self.atomic_write(filepath, content, invalidate_cache_after)
        except (TypeError, ValueError) as e:
            self.metrics["write_failures"] += 1
            logger.error(f"Atomic File Handler: JSON serialization error for {filepath}: {e}")
            return False


class AtomicFileSystemCog(commands.Cog, name="Atomic File System"):
    """
    Atomic File System diagnostics and monitoring
    Provides minimal commands for checking file handler health
    """
    
    def __init__(self, bot, file_handler: AtomicFileHandler):
        self.bot = bot
        self.handler = file_handler
        self.start_time = datetime.now()
        
        logger.info("Atomic File System Cog: Initialized")
    
    @commands.hybrid_command(name="atomicstats", help="Display atomic file system statistics (Bot Owner Only)")
    @commands.is_owner()
    async def atomic_stats_command(self, ctx):
        """Show comprehensive atomic file system statistics"""
        stats = self.handler.get_cache_stats()
        uptime = datetime.now() - self.start_time
        
        total_failures = stats['write_failures'] + stats['read_failures']
        total_ops = stats['total_reads'] + stats['total_writes']
        failure_rate = (total_failures / total_ops * 100) if total_ops > 0 else 0
        
        status = "Healthy" if failure_rate < 1 else "Degraded" if failure_rate < 5 else "Critical"
        status_color = 0x00ff00 if failure_rate < 1 else 0xffa500 if failure_rate < 5 else 0xff0000
        
        embed = discord.Embed(
            title="Atomic File System Statistics",
            description="Thread-safe file operations with LRU caching",
            color=status_color,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="Cache",
            value=f"```Size: {stats['cache_size']}/{stats['max_cache_size']}\nTTL: {stats['cache_ttl']}s\nHit Rate: {stats['hit_rate']}%\nHits: {stats['cache_hits']}\nMisses: {stats['cache_misses']}```",
            inline=True
        )
        
        embed.add_field(
            name="Locks",
            value=f"```Active: {stats['active_locks']}\nCleanups: {stats['lock_cleanups']}```",
            inline=True
        )
        
        embed.add_field(
            name="Operations",
            value=f"```Reads: {stats['total_reads']}\nWrites: {stats['total_writes']}\nInvalidations: {stats['cache_invalidations']}```",
            inline=True
        )
        
        embed.add_field(
            name="Health",
            value=f"```Status: {status}\nWrite Failures: {stats['write_failures']}\nRead Failures: {stats['read_failures']}\nFailure Rate: {failure_rate:.2f}%```",
            inline=False
        )
        
        embed.add_field(
            name="Uptime",
            value=f"```{str(uptime).split('.')[0]}```",
            inline=True
        )
        
        embed.set_footer(text="Atomic File System Diagnostics")
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    @commands.hybrid_command(name="atomictest", help="Test atomic file operations (Bot Owner Only)")
    @commands.is_owner()
    async def atomic_test_command(self, ctx):
        """Run comprehensive atomic file system tests"""
        test_file = "./data/atomic_test.json"
        test_data = {"test": "data", "timestamp": datetime.now().isoformat()}
        
        embed = discord.Embed(
            title="Atomic File System Test",
            description="Running comprehensive tests...",
            color=0xffa500,
            timestamp=discord.utils.utcnow()
        )
        
        msg = await ctx.send(embed=embed)
        
        results = []
        
        # Test 1: Write
        start = time.time()
        write_success = await self.handler.atomic_write_json(test_file, test_data)
        write_time = (time.time() - start) * 1000
        results.append(("Write Test", "PASS" if write_success else "FAIL", f"{write_time:.2f}ms"))
        
        # Test 2: Read (no cache)
        start = time.time()
        read_data = await self.handler.atomic_read_json(test_file, use_cache=False)
        read_time = (time.time() - start) * 1000
        read_success = read_data == test_data
        results.append(("Read Test (no cache)", "PASS" if read_success else "FAIL", f"{read_time:.2f}ms"))
        
        # Test 3: Read (with cache)
        start = time.time()
        cached_data = await self.handler.atomic_read_json(test_file, use_cache=True)
        cache_time = (time.time() - start) * 1000
        cache_success = cached_data == test_data
        results.append(("Read Test (cached)", "PASS" if cache_success else "FAIL", f"{cache_time:.2f}ms"))
        
        # Test 4: Concurrent writes
        concurrent_success = True
        start = time.time()
        try:
            tasks = [
                self.handler.atomic_write_json(test_file, {"concurrent": i})
                for i in range(10)
            ]
            await asyncio.gather(*tasks)
        except Exception as e:
            concurrent_success = False
            logger.error(f"Concurrent write test failed: {e}")
        concurrent_time = (time.time() - start) * 1000
        results.append(("Concurrent Writes (10x)", "PASS" if concurrent_success else "FAIL", f"{concurrent_time:.2f}ms"))
        
        # Test 5: Cache invalidation
        self.handler.invalidate_cache(test_file)
        start = time.time()
        invalidated_data = await self.handler.atomic_read_json(test_file, use_cache=True)
        invalidate_time = (time.time() - start) * 1000
        invalidate_success = invalidated_data is not None
        results.append(("Cache Invalidation", "PASS" if invalidate_success else "FAIL", f"{invalidate_time:.2f}ms"))
        
        # Cleanup
        try:
            os.remove(test_file)
        except:
            pass
        
        all_passed = all(status == "PASS" for _, status, _ in results)
        embed.color = 0x00ff00 if all_passed else 0xff0000
        embed.description = "Test Results"
        
        for test_name, status, timing in results:
            embed.add_field(
                name=f"[{status}] {test_name}",
                value=f"```{timing}```",
                inline=True
            )
        
        embed.add_field(
            name="Overall Status",
            value=f"```{'All tests passed' if all_passed else 'Some tests failed'}```",
            inline=False
        )
        
        await msg.edit(embed=embed)
        
        logger.info(f"Atomic File System: Tests completed by {ctx.author} - {'Passed' if all_passed else 'Failed'}")
    
    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        logger.info("Atomic File System Cog: Unloaded")


class SafeConfig:
    """Thread-safe configuration manager with atomic operations"""
    
    def __init__(self, config_path: str = "./config.json", file_handler: Optional[AtomicFileHandler] = None):
        self.config_path = config_path
        self.file_handler = file_handler or AtomicFileHandler()
        self.data = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize configuration from file"""
        if self._initialized:
            return
        self.data = await self._load_config()
        self._initialized = True
        logger.info(f"SafeConfig: Initialized from {self.config_path}")
    
    async def _load_config(self) -> dict:
        """Load configuration with defaults"""
        config = await self.file_handler.atomic_read_json(self.config_path)
        
        if config:
            logger.info("SafeConfig: Loaded existing configuration")
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
                "load_cogs": True,
                "enable_event_hooks": True,
                "enable_plugin_registry": True,
                "enable_framework_diagnostics": True,
                "enable_slash_command_limiter": True
            }
        }
        
        await self.save(default_config)
        logger.info("SafeConfig: Created default configuration")
        return default_config
    
    async def save(self, data: dict = None):
        """Save configuration atomically"""
        if data:
            self.data = data
        success = await self.file_handler.atomic_write_json(self.config_path, self.data)
        if success:
            logger.debug("SafeConfig: Configuration saved")
        else:
            logger.error("SafeConfig: Failed to save configuration")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot notation support"""
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
        """Set configuration value with dot notation support"""
        keys = key.split('.')
        data = self.data
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        data[keys[-1]] = value
        await self.save()
        logger.debug(f"SafeConfig: Set {key} = {value}")


class SafeDatabaseManager:
    """Thread-safe database manager with WAL mode and connection pooling"""
    
    def __init__(self, base_path: str = "./data", file_handler: Optional[AtomicFileHandler] = None):
        self.base_path = Path(base_path)
        self.file_handler = file_handler or AtomicFileHandler()
        self._guild_connections: Dict[int, Any] = {}
        self._connection_locks: Dict[int, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_path / "main.db"
        self.conn = None
        logger.info(f"SafeDatabaseManager: Initialized with base_path={base_path}")
    
    async def _get_guild_db_path(self, guild_id: int) -> Path:
        """Get database path for specific guild"""
        guild_folder = self.base_path / str(guild_id)
        guild_folder.mkdir(parents=True, exist_ok=True)
        return guild_folder / "guild.db"
    
    async def _create_tables(self, conn):
        """Create default guild database tables"""
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
        logger.debug(f"SafeDatabaseManager: Created tables for guild database")
    
    async def connect(self):
        """Connect to main database"""
        import aiosqlite
        if not self.conn:
            self.conn = await aiosqlite.connect(str(self.db_path))
            self.conn.row_factory = aiosqlite.Row
            await self.conn.execute("PRAGMA journal_mode=WAL")
            await self.conn.execute("PRAGMA synchronous=NORMAL")
            await self._create_main_tables()
            logger.info(f"SafeDatabaseManager: Connected to main database: {self.db_path}")

    async def _create_main_tables(self):
        """Create main database tables"""
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS global_stats (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.conn.commit()
        logger.debug("SafeDatabaseManager: Created main database tables")
    
    async def _get_guild_connection(self, guild_id: int):
        """Get or create connection for specific guild"""
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
                logger.info(f"SafeDatabaseManager: Created connection for guild {guild_id}")
            
            return self._guild_connections[guild_id]
    
    async def close(self):
        """Close all database connections"""
        async with self._global_lock:
            for guild_id, conn in list(self._guild_connections.items()):
                try:
                    await conn.close()
                    logger.info(f"SafeDatabaseManager: Closed connection for guild {guild_id}")
                except Exception as e:
                    logger.error(f"SafeDatabaseManager: Error closing guild {guild_id} connection: {e}")
            
            self._guild_connections.clear()
            
            if self.conn:
                await self.conn.close()
                self.conn = None
                logger.info("SafeDatabaseManager: Closed main database connection")
            
            self._connection_locks.clear()
    
    async def backup(self, guild_id: Optional[int] = None):
        """Create database backup"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if guild_id:
            db_path = await self._get_guild_db_path(guild_id)
            backup_path = db_path.parent / f"guild_backup_{timestamp}.db"
            try:
                if guild_id in self._guild_connections:
                    await self._guild_connections[guild_id].execute("PRAGMA wal_checkpoint(FULL)")
                shutil.copy2(db_path, backup_path)
                logger.info(f"SafeDatabaseManager: Database backed up for guild {guild_id}: {backup_path}")
                return True
            except Exception as e:
                logger.error(f"SafeDatabaseManager: Backup failed for guild {guild_id}: {e}")
                return False
        else:
            success_count = 0
            for gid in list(self._guild_connections.keys()):
                if await self.backup(gid):
                    success_count += 1
            logger.info(f"SafeDatabaseManager: Backed up {success_count}/{len(self._guild_connections)} guild databases")
            return True
    
    async def get_guild_prefix(self, guild_id: int) -> Optional[str]:
        """Get custom prefix for guild"""
        conn = await self._get_guild_connection(guild_id)
        
        try:
            async with conn.execute(
                "SELECT value FROM guild_settings WHERE key = 'prefix'"
            ) as cursor:
                row = await cursor.fetchone()
                return row['value'] if row else None
        except Exception as e:
            logger.error(f"SafeDatabaseManager: Error getting prefix for guild {guild_id}: {e}")
            return None
    
    async def set_guild_prefix(self, guild_id: int, prefix: str):
        """Set custom prefix for guild"""
        conn = await self._get_guild_connection(guild_id)
        
        try:
            await conn.execute(
                "INSERT OR REPLACE INTO guild_settings (key, value) VALUES ('prefix', ?)",
                (prefix,)
            )
            await conn.commit()
            logger.info(f"SafeDatabaseManager: Set prefix for guild {guild_id}: {prefix}")
        except Exception as e:
            logger.error(f"SafeDatabaseManager: Error setting prefix for guild {guild_id}: {e}")
    
    async def increment_command_usage(self, command_name: str):
        """Increment global command usage counter"""
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
            logger.error(f"SafeDatabaseManager: Failed to increment command usage: {e}")
    
    async def get_command_stats(self):
        """Get all command usage statistics"""
        if not self.conn:
            return []
        try:
            async with self.conn.execute(
                "SELECT key, value FROM global_stats WHERE key LIKE 'cmd_%'"
            ) as cursor:
                rows = await cursor.fetchall()
                return [(row['key'].replace('cmd_', ''), int(row['value'])) for row in rows]
        except Exception as e:
            logger.error(f"SafeDatabaseManager: Failed to get command stats: {e}")
            return []
    
    async def cleanup_guild(self, guild_id: int):
        """Cleanup guild database connection"""
        async with self._global_lock:
            if guild_id in self._guild_connections:
                try:
                    await self._guild_connections[guild_id].close()
                    del self._guild_connections[guild_id]
                    logger.info(f"SafeDatabaseManager: Cleaned up connection for guild {guild_id}")
                except Exception as e:
                    logger.error(f"SafeDatabaseManager: Error cleaning up guild {guild_id}: {e}")
            
            if guild_id in self._connection_locks:
                del self._connection_locks[guild_id]


class SafeLogRotator:
    """Safe log file rotation with size and age management"""
    
    def __init__(self, log_dir: str = "./botlogs", max_size: int = 10485760, backup_count: int = 5):
        self.log_dir = Path(log_dir)
        self.max_size = max_size
        self.backup_count = backup_count
        self.log_dir.mkdir(exist_ok=True)
        self._rotation_lock = asyncio.Lock()
        logger.info(f"SafeLogRotator: Initialized with max_size={max_size}, backup_count={backup_count}")
    
    async def should_rotate(self, log_file: Path) -> bool:
        """Check if log file should be rotated"""
        if not log_file.exists():
            return False
        return log_file.stat().st_size >= self.max_size
    
    async def rotate_log(self, log_file: Path):
        """Rotate log file with backup management"""
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
            
            logger.info(f"SafeLogRotator: Rotated log file: {log_file.name}")
    
    async def cleanup_old_logs(self, days: int = 30):
        """Remove log files older than specified days"""
        cutoff = datetime.now() - timedelta(days=days)
        removed_count = 0
        
        for log_file in self.log_dir.glob("*.log*"):
            try:
                if log_file.stat().st_mtime < cutoff.timestamp():
                    log_file.unlink()
                    removed_count += 1
                    logger.debug(f"SafeLogRotator: Removed old log: {log_file.name}")
            except Exception as e:
                logger.error(f"SafeLogRotator: Failed to remove {log_file.name}: {e}")
        
        if removed_count > 0:
            logger.info(f"SafeLogRotator: Removed {removed_count} old log files")


# Global instances
global_file_handler = AtomicFileHandler(cache_ttl=300, max_cache_size=1000)
global_log_rotator = SafeLogRotator()

"""
async def setup(bot):
    # Setup function for loading the cog
    await bot.add_cog(AtomicFileSystemCog(bot, global_file_handler))
    logger.info("Atomic File System cog loaded successfully")
"""