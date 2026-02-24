"""
# ===================================================================================
#
#   Copyright (c) 2026 TheHolyOneZ
#
#   This script is part of the ZDBF (Zoryx Discord Bot Framework).
#   This file is considered source-available and is not open-source.
#
#   You are granted permission to:
#   - View, read, and learn from this source code.
#   - Use this script 'as is' within the ZDBF.
#   - Run this script in multiple instances of your own ZDBF-based projects,
#     provided the license and script remain intact.
#
#   You are strictly prohibited from:
#   - Copying and pasting more than four (4) consecutive lines of this code
#     into other projects without explicit permission.
#   - Redistributing this script or any part of it. The only official source
#     is the GitHub repository: https://github.com/TheHolyOneZ/discord-bot-framework
#   - Modifying this license text.
#   - Removing any attribution or mention of the original author (TheHolyOneZ)
#     or the project names (ZDBF, TheZ).
#
#   This script is intended for use ONLY within the ZDBF ecosystem.
#   Use in any other framework is a direct violation of this license.
#
#   For issues, support, or feedback, please create an issue on the official
#   GitHub repository or contact the author through the official Discord server.
#
#   This software is provided "as is", without warranty of any kind, express or
#   implied, including but not limited to the warranties of merchantability,
#   fitness for a particular purpose and noninfringement. In no event shall the
#   authors or copyright holders be liable for any claim, damages or other
#   liability, whether in an action of contract, tort or otherwise, arising from,
#   out of or in connection with the software or the use or other dealings in the
#   software.
#
# ===================================================================================
"""
# Shard Manager - v1.0.0 | Created by TheHolyOneZ
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import asyncio
import os
import json
import time
import hashlib
import struct
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger('discord')

BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))


def is_bot_owner():
    """Check if user is the bot owner"""
    async def predicate(ctx):
        if ctx.author.id != BOT_OWNER_ID:
            raise commands.CheckFailure("This command is restricted to the bot owner only.")
        return True
    return commands.check(predicate)


class IPCMessage:
    """Represents an IPC message between shard clusters"""
    
    def __init__(self, op: str, data: dict, source: str = "", target: str = "all"):
        self.op = op
        self.data = data
        self.source = source
        self.target = target
        self.timestamp = time.time()
        self.nonce = hashlib.md5(f"{time.time()}{op}".encode()).hexdigest()[:12]
    
    def to_bytes(self) -> bytes:
        """Serialize to bytes for wire transport"""
        payload = json.dumps({
            'op': self.op,
            'data': self.data,
            'source': self.source,
            'target': self.target,
            'timestamp': self.timestamp,
            'nonce': self.nonce
        }).encode('utf-8')
        return struct.pack('>I', len(payload)) + payload
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'IPCMessage':
        """Deserialize from bytes"""
        payload = json.loads(data.decode('utf-8'))
        msg = cls(
            op=payload['op'],
            data=payload['data'],
            source=payload.get('source', 'unknown'),
            target=payload.get('target', 'all')
        )
        msg.timestamp = payload.get('timestamp', time.time())
        msg.nonce = payload.get('nonce', '')
        return msg
    
    def __repr__(self):
        return f"IPCMessage(op={self.op}, source={self.source}, target={self.target})"


class IPCServer:
    """
    WebSocket-like IPC server for the primary cluster.
    Secondary clusters connect to this server to form the mesh.
    """
    
    def __init__(self, host: str, port: int, secret: str, cluster_name: str):
        self.host = host
        self.port = port
        self.secret = secret
        self.cluster_name = cluster_name
        self.clients: Dict[str, asyncio.StreamWriter] = {}
        self.client_info: Dict[str, dict] = {}
        self._server: Optional[asyncio.AbstractServer] = None
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._running = False
        self._seen_nonces: set = set()
        self._max_nonces = 10000
    
    def on(self, op: str, handler: Callable):
        """Register a handler for an operation"""
        self._handlers[op].append(handler)
    
    async def start(self):
        """Start the IPC server"""
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        self._running = True
        logger.info(f"[IPC Server] Started on {self.host}:{self.port}")
    
    async def stop(self):
        """Stop the IPC server"""
        self._running = False
        
        for name, writer in list(self.clients.items()):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        
        self.clients.clear()
        self.client_info.clear()
        
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        logger.info("[IPC Server] Stopped")
    
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle an incoming client connection"""
        addr = writer.get_extra_info('peername')
        client_name = None
        
        try:
            raw = await asyncio.wait_for(self._read_message(reader), timeout=10.0)
            if not raw:
                writer.close()
                return
            
            msg = IPCMessage.from_bytes(raw)
            
            if msg.op != 'auth' or msg.data.get('secret') != self.secret:
                logger.warning(f"[IPC Server] Auth failed from {addr}")
                error_msg = IPCMessage('auth_response', {'success': False, 'error': 'Invalid secret'}, self.cluster_name)
                writer.write(error_msg.to_bytes())
                await writer.drain()
                writer.close()
                return
            
            client_name = msg.data.get('cluster_name', f'unknown-{addr}')
            self.clients[client_name] = writer
            self.client_info[client_name] = {
                'connected_at': time.time(),
                'address': str(addr),
                'shard_ids': msg.data.get('shard_ids', []),
                'shard_count': msg.data.get('shard_count', 0),
                'guild_count': msg.data.get('guild_count', 0),
                'last_heartbeat': time.time()
            }
            
            auth_ok = IPCMessage('auth_response', {
                'success': True,
                'server_cluster': self.cluster_name,
                'connected_clients': list(self.clients.keys())
            }, self.cluster_name)
            writer.write(auth_ok.to_bytes())
            await writer.drain()
            
            logger.info(f"[IPC Server] Client authenticated: {client_name} from {addr}")
            
            await self.broadcast(IPCMessage('cluster_join', {
                'cluster_name': client_name,
                'shard_ids': msg.data.get('shard_ids', [])
            }, self.cluster_name), exclude=client_name)
            
            while self._running:
                raw = await self._read_message(reader)
                if not raw:
                    break
                
                msg = IPCMessage.from_bytes(raw)
                msg.source = client_name
                
                if msg.nonce in self._seen_nonces:
                    continue
                self._seen_nonces.add(msg.nonce)
                if len(self._seen_nonces) > self._max_nonces:
                    self._seen_nonces = set(list(self._seen_nonces)[self._max_nonces // 2:])
                
                if msg.op == 'heartbeat':
                    if client_name in self.client_info:
                        self.client_info[client_name]['last_heartbeat'] = time.time()
                        self.client_info[client_name]['guild_count'] = msg.data.get('guild_count', 0)
                    
                    pong = IPCMessage('heartbeat_ack', {'timestamp': time.time()}, self.cluster_name, client_name)
                    writer.write(pong.to_bytes())
                    await writer.drain()
                    continue
                
                if msg.target == 'all':
                    await self.broadcast(msg, exclude=client_name)
                elif msg.target == self.cluster_name:
                    pass
                elif msg.target in self.clients:
                    await self._send_to(msg.target, msg)
                
                for handler in self._handlers.get(msg.op, []):
                    try:
                        await handler(msg)
                    except Exception as e:
                        logger.error(f"[IPC Server] Handler error for {msg.op}: {e}")
        
        except asyncio.TimeoutError:
            logger.warning(f"[IPC Server] Auth timeout from {addr}")
        except (ConnectionResetError, ConnectionError, asyncio.IncompleteReadError):
            pass
        except Exception as e:
            logger.error(f"[IPC Server] Client error: {e}")
        finally:
            if client_name:
                self.clients.pop(client_name, None)
                self.client_info.pop(client_name, None)
                logger.info(f"[IPC Server] Client disconnected: {client_name}")
                
                await self.broadcast(IPCMessage('cluster_leave', {
                    'cluster_name': client_name
                }, self.cluster_name))
            
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
    
    async def _read_message(self, reader: asyncio.StreamReader) -> Optional[bytes]:
        """Read a length-prefixed message"""
        try:
            length_bytes = await asyncio.wait_for(reader.readexactly(4), timeout=120.0)
            length = struct.unpack('>I', length_bytes)[0]
            
            if length > 1_000_000:
                logger.warning("[IPC Server] Message too large, dropping")
                return None
            
            data = await asyncio.wait_for(reader.readexactly(length), timeout=30.0)
            return data
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            return None
    
    async def broadcast(self, msg: IPCMessage, exclude: str = None):
        """Broadcast message to all connected clients"""
        data = msg.to_bytes()
        disconnected = []
        
        for name, writer in self.clients.items():
            if name == exclude:
                continue
            try:
                writer.write(data)
                await writer.drain()
            except Exception:
                disconnected.append(name)
        
        for name in disconnected:
            self.clients.pop(name, None)
            self.client_info.pop(name, None)
    
    async def _send_to(self, target: str, msg: IPCMessage):
        """Send message to a specific client"""
        writer = self.clients.get(target)
        if writer:
            try:
                writer.write(msg.to_bytes())
                await writer.drain()
            except Exception:
                self.clients.pop(target, None)
                self.client_info.pop(target, None)


class IPCClient:
    """
    IPC client for secondary clusters connecting to the primary.
    """
    
    def __init__(self, host: str, port: int, secret: str, cluster_name: str):
        self.host = host
        self.port = port
        self.secret = secret
        self.cluster_name = cluster_name
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._running = False
        self._connected = False
        self._reconnect_delay = 5
        self._max_reconnect_delay = 120
    
    def on(self, op: str, handler: Callable):
        """Register a handler for an operation"""
        self._handlers[op].append(handler)
    
    async def connect(self, shard_ids: list, shard_count: int, guild_count: int):
        """Connect to the IPC server"""
        self._running = True
        
        while self._running:
            try:
                self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
                
                auth = IPCMessage('auth', {
                    'secret': self.secret,
                    'cluster_name': self.cluster_name,
                    'shard_ids': shard_ids,
                    'shard_count': shard_count,
                    'guild_count': guild_count
                }, self.cluster_name)
                self._writer.write(auth.to_bytes())
                await self._writer.drain()
                
                raw = await self._read_message()
                if not raw:
                    raise ConnectionError("No auth response")
                
                response = IPCMessage.from_bytes(raw)
                if response.op != 'auth_response' or not response.data.get('success'):
                    error = response.data.get('error', 'Unknown')
                    logger.error(f"[IPC Client] Auth failed: {error}")
                    await asyncio.sleep(self._reconnect_delay)
                    continue
                
                self._connected = True
                self._reconnect_delay = 5
                logger.info(f"[IPC Client] Connected to IPC server at {self.host}:{self.port}")
                
                asyncio.create_task(self._heartbeat_loop(guild_count))
                
                while self._running:
                    raw = await self._read_message()
                    if not raw:
                        break
                    
                    msg = IPCMessage.from_bytes(raw)
                    
                    for handler in self._handlers.get(msg.op, []):
                        try:
                            await handler(msg)
                        except Exception as e:
                            logger.error(f"[IPC Client] Handler error for {msg.op}: {e}")
            
            except (ConnectionRefusedError, OSError) as e:
                logger.warning(f"[IPC Client] Connection failed: {e} — retrying in {self._reconnect_delay}s")
            except Exception as e:
                logger.error(f"[IPC Client] Error: {e}")
            finally:
                self._connected = False
                if self._writer:
                    try:
                        self._writer.close()
                        await self._writer.wait_closed()
                    except Exception:
                        pass
            
            if self._running:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
    
    async def send(self, msg: IPCMessage):
        """Send a message to the IPC server"""
        if not self._connected or not self._writer:
            return False
        try:
            msg.source = self.cluster_name
            self._writer.write(msg.to_bytes())
            await self._writer.drain()
            return True
        except Exception:
            self._connected = False
            return False
    
    async def _read_message(self) -> Optional[bytes]:
        """Read a length-prefixed message"""
        try:
            length_bytes = await asyncio.wait_for(self._reader.readexactly(4), timeout=120.0)
            length = struct.unpack('>I', length_bytes)[0]
            if length > 1_000_000:
                return None
            data = await asyncio.wait_for(self._reader.readexactly(length), timeout=30.0)
            return data
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            return None
    
    async def _heartbeat_loop(self, guild_count: int):
        """Send periodic heartbeats"""
        while self._running and self._connected:
            try:
                hb = IPCMessage('heartbeat', {
                    'timestamp': time.time(),
                    'guild_count': guild_count
                }, self.cluster_name)
                await self.send(hb)
                await asyncio.sleep(30)
            except Exception:
                break
    
    async def close(self):
        """Close the connection"""
        self._running = False
        self._connected = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass


class ShardManager(commands.Cog):
    """
    Multi-Process Shard Management System (Bot Owner Only)
    
    Enables cross-shard communication via lightweight IPC.
    Run one cluster as 'server' mode and additional clusters as 'client' mode.
    
    All commands restricted to BOT_OWNER_ID.
    Toggle via ENABLE_SHARD_MANAGER in .env
    """
    
    def __init__(self, bot):
        self.bot = bot
        
        self.ipc_host = os.getenv("SHARD_IPC_HOST", "127.0.0.1")
        self.ipc_port = int(os.getenv("SHARD_IPC_PORT", 20000))
        self.ipc_secret = os.getenv("SHARD_IPC_SECRET", "change_me_please")
        self.ipc_mode = os.getenv("SHARD_IPC_MODE", "server").lower()
        self.cluster_name = os.getenv("SHARD_CLUSTER_NAME", "cluster-0")
        
        self.ipc_server: Optional[IPCServer] = None
        self.ipc_client: Optional[IPCClient] = None
        
        self.cluster_stats: Dict[str, dict] = {}
        self.cross_shard_requests: Dict[str, asyncio.Future] = {}
        
        self.data_dir = Path("./data/shard_manager")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[ShardManager] Initialized | Mode: {self.ipc_mode} | Cluster: {self.cluster_name}")
    
    async def cog_load(self):
        """Start IPC system"""
        if self.ipc_mode == "server":
            await self._start_server()
        else:
            await self._start_client()
        
        self.sync_stats.start()
        logger.info("[ShardManager] IPC system started")
    
    def cog_unload(self):
        """Stop IPC system"""
        self.sync_stats.cancel()
        asyncio.create_task(self._shutdown_ipc())
    
    async def _start_server(self):
        """Start as IPC server (primary cluster)"""
        self.ipc_server = IPCServer(self.ipc_host, self.ipc_port, self.ipc_secret, self.cluster_name)
        
        self.ipc_server.on('stats_request', self._handle_stats_request)
        self.ipc_server.on('stats_broadcast', self._handle_stats_broadcast)
        self.ipc_server.on('guild_count_request', self._handle_guild_count_request)
        self.ipc_server.on('eval_request', self._handle_eval_request)
        
        await self.ipc_server.start()
    
    async def _start_client(self):
        """Start as IPC client (secondary cluster)"""
        self.ipc_client = IPCClient(self.ipc_host, self.ipc_port, self.ipc_secret, self.cluster_name)
        
        self.ipc_client.on('stats_request', self._handle_stats_request)
        self.ipc_client.on('guild_count_request', self._handle_guild_count_request)
        self.ipc_client.on('stats_broadcast', self._handle_stats_broadcast)
        
        shard_ids = list(self.bot.shards.keys()) if self.bot.shards else [0]
        asyncio.create_task(self.ipc_client.connect(
            shard_ids=shard_ids,
            shard_count=self.bot.shard_count,
            guild_count=len(self.bot.guilds)
        ))
    
    async def _shutdown_ipc(self):
        """Shutdown IPC connections"""
        if self.ipc_server:
            await self.ipc_server.stop()
        if self.ipc_client:
            await self.ipc_client.close()
        logger.info("[ShardManager] IPC shutdown complete")
    
    
    async def _handle_stats_request(self, msg: IPCMessage):
        """Handle a stats request from another cluster"""
        stats = self._get_local_stats()
        response = IPCMessage('stats_broadcast', stats, self.cluster_name, msg.source)
        
        if self.ipc_server:
            await self.ipc_server._send_to(msg.source, response)
        elif self.ipc_client:
            await self.ipc_client.send(response)
    
    async def _handle_stats_broadcast(self, msg: IPCMessage):
        """Handle stats broadcast from another cluster"""
        self.cluster_stats[msg.source] = {
            **msg.data,
            'last_update': time.time()
        }
    
    async def _handle_guild_count_request(self, msg: IPCMessage):
        """Handle guild count request"""
        response = IPCMessage('guild_count_response', {
            'guild_count': len(self.bot.guilds),
            'user_count': len(self.bot.users),
            'shard_count': self.bot.shard_count
        }, self.cluster_name, msg.source)
        
        if self.ipc_server:
            await self.ipc_server._send_to(msg.source, response)
        elif self.ipc_client:
            await self.ipc_client.send(response)
    
    async def _handle_eval_request(self, msg: IPCMessage):
        """Handle eval request (owner safety: only preset queries)"""
        query = msg.data.get('query', '')
        
        safe_queries = {
            'guild_count': len(self.bot.guilds),
            'user_count': len(self.bot.users),
            'shard_count': self.bot.shard_count,
            'latency': self.bot.latency,
            'uptime': time.time() - self.bot.metrics.start_time if hasattr(self.bot, 'metrics') else 0,
        }
        
        result = safe_queries.get(query, 'unknown_query')
        response = IPCMessage('eval_response', {
            'query': query,
            'result': result
        }, self.cluster_name, msg.source)
        
        if self.ipc_server:
            await self.ipc_server._send_to(msg.source, response)
        elif self.ipc_client:
            await self.ipc_client.send(response)
    
    def _get_local_stats(self) -> dict:
        """Get stats for this cluster"""
        shard_ids = list(self.bot.shards.keys()) if self.bot.shards else [0]
        
        return {
            'cluster_name': self.cluster_name,
            'guild_count': len(self.bot.guilds),
            'user_count': len(self.bot.users),
            'shard_count': self.bot.shard_count,
            'shard_ids': shard_ids,
            'latency': self.bot.latency,
            'uptime': time.time() - self.bot.metrics.start_time if hasattr(self.bot, 'metrics') else 0,
            'mode': self.ipc_mode,
            'timestamp': time.time()
        }
    
    
    @tasks.loop(minutes=1)
    async def sync_stats(self):
        """Periodically broadcast stats to all clusters"""
        stats = self._get_local_stats()
        msg = IPCMessage('stats_broadcast', stats, self.cluster_name)
        
        if self.ipc_server:
            await self.ipc_server.broadcast(msg)
        elif self.ipc_client:
            await self.ipc_client.send(msg)
        
        self.cluster_stats[self.cluster_name] = {
            **stats,
            'last_update': time.time()
        }
    
    @sync_stats.before_loop
    async def before_sync_stats(self):
        await self.bot.wait_until_ready()
    
    
    @commands.hybrid_command(
        name="clusters",
        help="Show all connected shard clusters and their status (Bot Owner Only)"
    )
    @is_bot_owner()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def clusters_cmd(self, ctx):
        """Display all connected clusters"""
        
        embed = discord.Embed(
            title="🌐 Shard Cluster Overview",
            description=f"**Mode: `{self.ipc_mode}` | This Cluster: `{self.cluster_name}`**",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        local = self._get_local_stats()
        uptime_str = str(timedelta(seconds=int(local['uptime'])))
        
        embed.add_field(
            name=f"🟢 {self.cluster_name} (This)",
            value=(
                f"```\n"
                f"Guilds:  {local['guild_count']:,}\n"
                f"Users:   {local['user_count']:,}\n"
                f"Shards:  {local['shard_count']} ({', '.join(str(s) for s in local['shard_ids'])})\n"
                f"Latency: {local['latency']*1000:.1f}ms\n"
                f"Uptime:  {uptime_str}\n"
                f"```"
            ),
            inline=True
        )
        
        if self.ipc_server:
            for name, info in self.ipc_server.client_info.items():
                time_ago = time.time() - info.get('last_heartbeat', 0)
                status = "🟢" if time_ago < 60 else ("🟡" if time_ago < 180 else "🔴")
                
                remote_stats = self.cluster_stats.get(name, {})
                
                embed.add_field(
                    name=f"{status} {name}",
                    value=(
                        f"```\n"
                        f"Guilds:    {remote_stats.get('guild_count', info.get('guild_count', '?')):,}\n"
                        f"Shards:    {info.get('shard_count', '?')} ({', '.join(str(s) for s in info.get('shard_ids', []))})\n"
                        f"Heartbeat: {time_ago:.0f}s ago\n"
                        f"Connected: {datetime.fromtimestamp(info.get('connected_at', 0)).strftime('%H:%M:%S')}\n"
                        f"```"
                    ),
                    inline=True
                )
        
        for name, stats in self.cluster_stats.items():
            if name == self.cluster_name:
                continue
            if self.ipc_server and name in self.ipc_server.client_info:
                continue
            
            time_ago = time.time() - stats.get('last_update', 0)
            if time_ago > 300:
                continue
            
            status = "🟢" if time_ago < 120 else "🟡"
            embed.add_field(
                name=f"{status} {name}",
                value=(
                    f"```\n"
                    f"Guilds:  {stats.get('guild_count', '?'):,}\n"
                    f"Shards:  {stats.get('shard_count', '?')}\n"
                    f"Updated: {time_ago:.0f}s ago\n"
                    f"```"
                ),
                inline=True
            )
        
        total_guilds = local['guild_count']
        total_users = local['user_count']
        total_shards = local['shard_count']
        cluster_count = 1
        
        for name, stats in self.cluster_stats.items():
            if name == self.cluster_name:
                continue
            if time.time() - stats.get('last_update', 0) < 300:
                total_guilds += stats.get('guild_count', 0)
                total_users += stats.get('user_count', 0)
                total_shards += stats.get('shard_count', 0)
                cluster_count += 1
        
        embed.add_field(
            name="📊 Global Totals",
            value=(
                f"```\n"
                f"Clusters: {cluster_count}\n"
                f"Guilds:   {total_guilds:,}\n"
                f"Users:    {total_users:,}\n"
                f"Shards:   {total_shards}\n"
                f"```"
            ),
            inline=False
        )
        
        if self.ipc_server:
            embed.add_field(
                name="🔌 IPC Server Status",
                value=f"```Listening: {self.ipc_host}:{self.ipc_port}\nClients:   {len(self.ipc_server.clients)}```",
                inline=False
            )
        elif self.ipc_client:
            conn_status = "Connected" if self.ipc_client._connected else "Disconnected"
            embed.add_field(
                name="🔌 IPC Client Status",
                value=f"```Server:  {self.ipc_host}:{self.ipc_port}\nStatus:  {conn_status}```",
                inline=False
            )
        
        embed.set_footer(text=f"Bot Owner Only • {ctx.author}")
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="ipcstatus",
        help="Show IPC connection status and diagnostics (Bot Owner Only)"
    )
    @is_bot_owner()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ipc_status(self, ctx):
        """Show IPC system diagnostics"""
        
        embed = discord.Embed(
            title="🔌 IPC System Status",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="⚙️ Configuration",
            value=(
                f"```\n"
                f"Mode:    {self.ipc_mode}\n"
                f"Cluster: {self.cluster_name}\n"
                f"Host:    {self.ipc_host}\n"
                f"Port:    {self.ipc_port}\n"
                f"Secret:  {'*' * len(self.ipc_secret[:4])}{'...' if len(self.ipc_secret) > 4 else ''}\n"
                f"```"
            ),
            inline=False
        )
        
        if self.ipc_server:
            clients_info = []
            for name, info in self.ipc_server.client_info.items():
                time_ago = time.time() - info.get('last_heartbeat', 0)
                clients_info.append(f"  {name}: {time_ago:.0f}s ago from {info.get('address', '?')}")
            
            embed.add_field(
                name=f"📡 Server — {len(self.ipc_server.clients)} client(s)",
                value="```" + ("\n".join(clients_info) if clients_info else "No clients connected") + "```",
                inline=False
            )
        
        if self.ipc_client:
            embed.add_field(
                name="📡 Client Connection",
                value=f"```Connected: {self.ipc_client._connected}\nTarget:    {self.ipc_host}:{self.ipc_port}```",
                inline=False
            )
        
        embed.set_footer(text=f"Bot Owner Only • {ctx.author}")
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="broadcastmsg",
        help="Broadcast a message to all clusters (Bot Owner Only)"
    )
    @is_bot_owner()
    @app_commands.describe(message="Message to broadcast to all clusters")
    async def broadcast_msg(self, ctx, *, message: str):
        """Send a broadcast message to all connected clusters"""
        
        msg = IPCMessage('broadcast_message', {
            'message': message[:500],
            'author': str(ctx.author),
            'author_id': ctx.author.id
        }, self.cluster_name)
        
        sent_to = 0
        if self.ipc_server:
            await self.ipc_server.broadcast(msg)
            sent_to = len(self.ipc_server.clients)
        elif self.ipc_client:
            success = await self.ipc_client.send(msg)
            sent_to = 1 if success else 0
        
        embed = discord.Embed(
            title="📢 Broadcast Sent",
            description=f"```{message[:500]}```",
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="📡 Delivered To", value=f"```{sent_to} cluster(s)```")
        embed.set_footer(text=f"Bot Owner Only • {ctx.author}")
        await ctx.send(embed=embed)


async def setup(bot):
    """Load the ShardManager cog (respects ENABLE_SHARD_MANAGER env var)"""
    enabled = os.getenv("ENABLE_SHARD_MANAGER", "false").lower()
    
    if enabled not in ("true", "1", "yes"):
        logger.info("ShardManager cog is DISABLED via ENABLE_SHARD_MANAGER env var")
        return
    
    secret = os.getenv("SHARD_IPC_SECRET", "change_me_please")
    if secret == "change_me_please":
        logger.warning("[ShardManager] Using default IPC secret! Set SHARD_IPC_SECRET in .env for security!")
    
    await bot.add_cog(ShardManager(bot))
    logger.info("ShardManager cog setup complete")