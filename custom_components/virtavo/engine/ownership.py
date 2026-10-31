"""Playback identity recovered from the APK's device-name parser.

No network, owner-ID guesses or stored key. Metadata from group 1 is shared.
The app encodes shared names as displayName@shareName, splitting the FIRST @.
The username passed to playback is the sharer's name for a shared device.
"""
from dataclasses import dataclass, field


def _name_bytes(value, label):
    if isinstance(value, str):
        value = value.encode('utf-8')
    if not isinstance(value, bytes) or b'\0' in value:
        raise ValueError('Invalid ' + label)
    return value


def account_play_username(canonical_username):
    """APK getUserNameNoPrefix, retaining the original login field elsewhere.

    Only when it starts '#', the app removes every occurrence of its three
    explicit platform markers. An unknown marker is not guessed or stripped.
    Shared metadata's shareName is passed directly and does not use this getter.
    """
    name = _name_bytes(canonical_username, 'canonical account name')
    if name.startswith(b'#'):
        for marker in (b'#virtavo#', b'#yuanli#', b'#_360eyes#'):
            name = name.replace(marker, b'')
    return name


@dataclass(frozen=True)
class PlaybackIdentity:
    display_name: str
    owner_type: int
    canonical_username: bytes = field(repr=False)
    share_name: bytes = field(repr=False)
    raw_name: bytes = field(repr=False)

    @property
    def is_shared(self):
        return self.owner_type == 1

    @property
    def play_username(self):
        """Caller-supplied app account name or metadata's sharer name bytes.

        No fallback from missing shared identity to the currently logged-in
        account: that would derive a valid-looking but wrong DES input.
        """
        name = self.share_name if self.is_shared else account_play_username(self.canonical_username)
        if not name:
            raise ValueError('Playback username is unavailable')
        return name


def parse_device_identity(raw_name, canonical_username, own_type):
    """Parse metadata without mutating the canonical account response.

    own_type is the discovery group. A first @ in metadata independently marks
    the device shared, exactly as DeviceDataUtil.parseDeviceBaseName does.
    Canonical username must be the account name used by AppClient.getUserName;
    prefix handling can be applied separately, without changing NetSession.
    """
    if type(own_type) is not int or own_type not in (0, 1):
        raise ValueError('Unsupported ownership group')
    raw = _name_bytes(raw_name, 'device name')
    canonical = _name_bytes(canonical_username, 'canonical account name')
    if b'@' in raw:
        display, share = raw.split(b'@', 1)
        group = 1
    else:
        display, share, group = raw, b'', own_type
    return PlaybackIdentity(display.decode('utf-8', errors='replace'), group,
                            canonical, share, raw)


def shared_owner_request(session, device_id, *, device_type, own_type, revision=4836):
    """10108 owner query from a fresh session, without changing manager owner.

    Native JNI passes deviceType1/ownType1 for shared-owner lookup. The caller
    supplies those values explicitly to preserve the derivation's scope.
    """
    return device_owner_request(session.user_id, session.session, device_id,
                                device_type, own_type, revision=revision)


def device_owner_request(user_id, session, device_id, device_type, own_type, *, revision=4836):
    """Native10108 request: current uid + explicit query + fresh session128."""
    import struct
    for value, bits in ((user_id,32),(device_id,32),(device_type,32),
                        (own_type,32),(revision,16)):
        if type(value) is not int or not 0 <= value < 1 << bits:
            raise ValueError('Invalid owner query field')
    token = session
    if not isinstance(token,bytes) or len(token)!=128 or not any(token):
        raise ValueError('Fresh NET session required')
    body=struct.pack('<IIII',user_id,device_id,device_type,own_type)+token
    return struct.pack('<4sIHHII',bytes.fromhex('ccddeeff'),10108,revision,105,164,0)+body


def parse_shared_owner_response(packet):
    """Return ownerUserId from the native 24-byte 10108 response body.

    Remaining words are left uninterpreted. This does not replace the current
    authenticated owner_client_id used by manager sign-in or relay requests.
    """
    import struct
    if not isinstance(packet,bytes) or len(packet)!=44:
        raise ValueError('Invalid owner response size')
    magic,command,revision,version,total,status=struct.unpack_from('<4sIHHII',packet)
    if magic!=bytes.fromhex('ccddeeff') or command!=10108 or total!=44 or status:
        raise ValueError('Invalid owner response header')
    owner=struct.unpack_from('<I',packet,24)[0]
    if not owner:
        raise ValueError('Owner identity unavailable')
    return owner



def parse_device_owner(packet):
    """Named API alias returning only the shared device's ownerUserId."""
    return parse_shared_owner_response(packet)
