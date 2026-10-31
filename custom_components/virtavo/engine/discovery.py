"""Bounded discovery transactions over an already authenticated connection.

Explicit query semantics are supplied by the caller; this layer validates
response consistency and never wakes or starts a camera.
"""
from dataclasses import dataclass,field
from . import device_protocol as wire

@dataclass(frozen=True)
class DeviceQuery:
    username:bytes=field(repr=False)
    device_type:int
    own_type:int
    order_by:int
    descending:int


def discover_devices(connection,query,*,max_devices=500):
    if type(max_devices) is not int or not 1<=max_devices<=65535:
        raise ValueError('Invalid discovery limit')
    if not isinstance(query,DeviceQuery):raise TypeError('DeviceQuery required')
    session=connection.session
    ids=[]
    total=None
    offset=0
    while total is None or offset<total:
        request=wire.device_ids_request(session.user_id,session.session,query.username,
             device_type=query.device_type,own_type=query.own_type,offset=offset,
             count=min(50,max_devices-offset),order_by=query.order_by,descending=query.descending)
        reply=connection.request(request,expected_command=10048)
        page=wire.parse_device_ids(reply)
        if page.offset!=offset or page.total>max_devices or (total is not None and page.total!=total):
            raise ValueError('Inconsistent discovery page')
        if page.order_by!=query.order_by or page.descending!=query.descending:
            raise ValueError('Unexpected discovery ordering')
        total=page.total
        if not page.device_ids and offset<total:raise ValueError('Discovery made no progress')
        if offset+len(page.device_ids)>total:raise ValueError('Discovery exceeded declared total')
        for device_id in page.device_ids:
            if not device_id or device_id in ids:raise ValueError('Invalid or duplicate device identity')
            ids.append(device_id)
        offset+=len(page.device_ids)
        if offset>=max_devices and offset<total:raise ValueError('Discovery limit reached')
    devices=[]
    for device_id in ids:
        request=wire.device_info_request(session.user_id,session.session,device_id,
                           device_type=query.device_type,own_type=query.own_type)
        info=wire.parse_device_info(connection.request(request,expected_command=10049))
        if info.device_id!=device_id:raise ValueError('Device metadata identity mismatch')
        devices.append(info)
    return tuple(devices)


@dataclass(frozen=True)
class AccountDiscovery:
    devices: tuple = field(repr=False)
    owner_type_counts: tuple[tuple[int,int],...]
    duplicate_ids: int
    discovery_name_changed: bool
    device_owner_types: tuple[tuple[int,int],...] = field(repr=False,default=())


def username_no_prefix(canonical_username):
    """Match PwAccountLoginRsp.getUserNameNoPrefix(), without altering session.

    Prefix removal is also useful to callers that need the app's canonical name
    for play parameters. Discovery lowercasing is a separate app operation.
    """
    if not isinstance(canonical_username,bytes) or not canonical_username or b'\0' in canonical_username:
        raise ValueError('Canonical account name required')
    name=canonical_username.decode('utf-8')
    if name.startswith('#'):
        for prefix in ('#virtavo#','#yuanli#','#_360eyes#'):
            name=name.replace(prefix,'')
    if not name:raise ValueError('Empty normalized account name')
    return name.encode('utf-8')


def account_discovery_username(canonical_username):
    """Supplied APK has an empty platform prefix; toPlatformUsername lowercases."""
    name=username_no_prefix(canonical_username).decode('utf-8').lower().encode('utf-8')
    # Same64-byte C-string constraint as the wire producer; don't silently truncate.
    if len(name)>=64:raise ValueError('Normalized account name exceeds wire field')
    return name


def discover_account_devices(connection,*,max_devices=500):
    """Mirror PwDeviceRequest.getDeviceList(): query ownType0 AND1.

    Metadata is fetched with the same ownership selector used for each list.
    A device present in both lists is returned once, preferring the first list.
    Counts retain both raw groups so a second empty result remains diagnosable.
    """
    canonical=connection.session.canonical_username
    name=account_discovery_username(canonical)
    found=[]
    seen=set()
    counts=[]
    duplicates=0
    ownership=[]
    for owner_type in (0,1):
        query=DeviceQuery(name,device_type=1,own_type=owner_type,order_by=2,descending=0)
        devices=discover_devices(connection,query,max_devices=max_devices)
        counts.append((owner_type,len(devices)))
        for device in devices:
            if device.device_id in seen:
                duplicates+=1
                continue
            if len(found)>=max_devices:raise ValueError('Combined discovery limit reached')
            found.append(device)
            ownership.append((device.device_id,owner_type))
            seen.add(device.device_id)
    return AccountDiscovery(tuple(found),tuple(counts),duplicates,name!=canonical,tuple(ownership))
