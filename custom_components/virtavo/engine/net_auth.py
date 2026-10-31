"""NET V2 authentication used by IPC360 Home 8.10.1.0.

Fresh salt/login and manager sign-in, with no SDK, PCAP or captured session.
Only explicit connect/authenticate calls open sockets. See docs/PROTOCOL.md.
"""
from dataclasses import dataclass, field
import hashlib
import math
import socket
import struct
import time

MAGIC = bytes.fromhex('ccddeeff')
HEADER = struct.Struct('<4sIHHII')
MAX_FRAME = 65536


class ProtocolError(ValueError):
    """Malformed or unsupported response. Messages contain no payloads."""


class AuthenticationError(ValueError):
    """The authentication server rejected a request."""


@dataclass(frozen=True)
class Message:
    command: int
    status: int
    payload: bytes = field(repr=False)


@dataclass(frozen=True)
class NetSession:
    user_id: int = field(repr=False)
    owner_client_id: int = field(repr=False)
    custom_id: int = field(repr=False)
    manager_ip_raw: int = field(repr=False)
    manager_port: int
    session: bytes = field(repr=False)
    canonical_username: bytes = field(repr=False)

    @property
    def manager_host(self):
        return socket.inet_ntoa(struct.pack('<I', self.manager_ip_raw))


def _uint(value, bits):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError('integer protocol field out of range')
    return value


def _cstring(value, size, *, allow_empty=False):
    if isinstance(value, str):
        value = value.encode('utf-8')
    if (not isinstance(value, bytes) or b'\0' in value or len(value) >= size
            or (not value and not allow_empty)):
        raise ValueError('invalid string field')
    return value.ljust(size, b'\0')


def frame(command, payload, *, revision, version=105):
    if not isinstance(payload, bytes) or len(payload) > MAX_FRAME - HEADER.size:
        raise ValueError('invalid payload size')
    return HEADER.pack(MAGIC, _uint(command, 32), _uint(revision, 16),
                       _uint(version, 16), 20 + len(payload), 0) + payload


def parse_frame(data):
    if not isinstance(data, bytes) or not 20 <= len(data) <= MAX_FRAME:
        raise ProtocolError('invalid frame size')
    magic, command, revision, version, total, status = HEADER.unpack_from(data)
    if magic != MAGIC or total != len(data):
        raise ProtocolError('invalid frame header')
    return Message(command, status, data[20:])


def salt_request(account, *, revision, version=105):
    return frame(10030, _cstring(account, 64) + struct.pack('<H', 1),
                 revision=revision, version=version)


def password_hash(password, salt):
    raw = _cstring(password, 64).split(b'\0', 1)[0]
    if not isinstance(salt, bytes) or len(salt) != 16:
        raise ValueError('salt must be 16 bytes')
    salt = salt.split(b'\0', 1)[0]
    first = hashlib.md5(raw).hexdigest().encode('ascii')
    return hashlib.md5(first + salt).hexdigest().encode('ascii')


def login_request(account, password, salt, *, language, user_type, os_type,
                  revision, token=b'', token_type=0, version=105):
    payload = (
        _cstring(account, 64) + password_hash(password, salt).ljust(64, b'\0')
        + struct.pack('<HHI', _uint(language, 16), _uint(user_type, 16),
                      _uint(os_type, 32))
        + _cstring(token, 192, allow_empty=True)
        + struct.pack('<I', _uint(token_type, 32))
    )
    return frame(10120, payload, revision=revision, version=version)


def _response(message, command, size):
    if not isinstance(message, Message) or message.command != command:
        raise ProtocolError('unexpected response command')
    if message.status != 0:
        raise AuthenticationError('authentication response rejected')
    if len(message.payload) != size:
        raise ProtocolError('unexpected response length')
    return message.payload


def parse_salt(message):
    # Native 10030 handler checks 36 total bytes, not 56.
    return _response(message, 10030, 16)


def parse_login(message):
    payload = _response(message, 10120, 220)
    user_id, manager_ip, manager_port, custom_id = struct.unpack_from('<IIII', payload)
    # This is opaque binary session material; NUL bytes are meaningful.
    session = payload[24:152]
    canonical_username = payload[156:220].split(b'\0', 1)[0]
    if (not user_id or not any(session) or not manager_ip
            or not 1 <= manager_port <= 65535):
        raise ProtocolError('login has no usable session or endpoint')
    return NetSession(user_id, user_id, custom_id, manager_ip, manager_port,
                      session, canonical_username)


def read_exact(sock, size, *, deadline=None):
    if type(size) is not int or not 0 <= size <= MAX_FRAME:
        raise ProtocolError('invalid read size')
    output = bytearray()
    while len(output) < size:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('response deadline exceeded')
            sock.settimeout(remaining)
        chunk = sock.recv(size - len(output))
        if not chunk:
            raise ConnectionError('connection closed before complete frame')
        output.extend(chunk)
    return bytes(output)


def exchange_raw(sock, request, *, timeout=None):
    """One serialized exchange, returning the complete validated wire frame."""
    parse_frame(request)  # Do not transmit malformed locally generated frames.
    if timeout is not None:
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('invalid timeout')
        deadline = time.monotonic() + timeout
        sock.settimeout(timeout)
    else:
        deadline = None
    sock.sendall(request)
    header = read_exact(sock, 20, deadline=deadline)
    magic, command, revision, version, total, status = HEADER.unpack(header)
    if magic != MAGIC or not 20 <= total <= MAX_FRAME:
        raise ProtocolError('invalid response header')
    raw = header + read_exact(sock, total - 20, deadline=deadline)
    parse_frame(raw)
    return raw


def exchange(sock, request, *, timeout=None):
    return parse_frame(exchange_raw(sock, request, timeout=timeout))


def _validate_connection(host, port, timeout):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('invalid bootstrap port')
    if not isinstance(host, str) or not host or '\0' in host:
        raise ValueError('bootstrap host is required')
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or timeout <= 0):
        raise ValueError('invalid timeout')


class NetConnection:
    """Owned authenticated NET connection for sequential discovery requests.

    The owner must serialize calls and close the context. This synchronous API
    belongs in a HA executor; it must not run on the Home Assistant event loop.
    It does not log or write account/session material.
    """
    def __init__(self, sock, session, *, timeout=8):
        self._socket = sock
        self.session = session
        self._timeout = timeout

    @classmethod
    def connect(cls, host, account, password, *, language, user_type, os_type,
                revision, token=b'', token_type=0, port=19000, timeout=8,
                version=105):
        first = salt_request(account, revision=revision, version=version)
        # Validate every local field before opening a socket.
        login_request(account, password, bytes(16), language=language,
                      user_type=user_type, os_type=os_type, revision=revision,
                      token=token, token_type=token_type, version=version)
        _validate_connection(host, port, timeout)
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            sock.settimeout(timeout)
            salt = parse_salt(exchange(sock, first, timeout=timeout))
            request = login_request(account, password, salt, language=language,
                                    user_type=user_type, os_type=os_type,
                                    revision=revision, token=token,
                                    token_type=token_type, version=version)
            session = parse_login(exchange(sock, request, timeout=timeout))
        except BaseException:
            sock.close()
            raise
        return cls(sock, session, timeout=timeout)

    def request(self, request, expected_command=None):
        if self._socket is None:
            raise ConnectionError('connection is closed')
        if expected_command is not None:
            _uint(expected_command, 32)
        try:
            raw = exchange_raw(self._socket, request, timeout=self._timeout)
            message = parse_frame(raw)
            if expected_command is not None and message.command != expected_command:
                raise ProtocolError('unexpected response command')
            if message.status != 0:
                raise ProtocolError('remote request rejected')
            return raw
        except BaseException:
            # An error leaves response association uncertain; never reuse the
            # connection to risk treating a delayed reply as a fresh response.
            self.close()
            raise

    def close(self):
        sock, self._socket = self._socket, None
        if sock is not None:
            sock.close()

    def __enter__(self):
        if self._socket is None:
            raise ConnectionError('connection is closed')
        return self

    def __exit__(self, *exc):
        self.close()


def authenticate(host, account, password, *, language, user_type, os_type,
                 revision, token=b'', token_type=0, port=19000, timeout=8,
                 version=105):
    """Fresh login only. Persistent discovery owners should use NetConnection."""
    with NetConnection.connect(host, account, password, language=language,
                               user_type=user_type, os_type=os_type,
                               revision=revision, token=token,
                               token_type=token_type, port=port, timeout=timeout,
                               version=version) as connection:
        return connection.session


def manager_signin(session: NetSession, *, access_sign_in_type, device_magic,
                   revision):
    """NET manager sign-in: version 106, body 148, opaque session 128.

    Native selects command 20425 only for access_sign_in_type 5; normally 20200.
    Caller supplies actual init fields; values are not inferred from a capture.
    """
    if (not isinstance(session, NetSession)
            or not isinstance(session.session, bytes) or len(session.session) != 128
            or not any(session.session)):
        raise ValueError('NET session128 is required')
    access = _uint(access_sign_in_type, 8)
    payload = (
        struct.pack('<HHIIII', 1, (access << 8) | 1,
                    _uint(session.custom_id, 32),
                    _uint(session.owner_client_id, 32), 0,
                    _uint(device_magic, 32)) + session.session
    )
    command = 20425 if access == 5 else 20200
    return frame(command, payload, revision=revision, version=106)
