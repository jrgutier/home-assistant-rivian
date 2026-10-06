from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PetSnapshotSecureFile(_message.Message):
    __slots__ = ("metadata",)
    class FileType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        FILE_TYPE_UNSPECIFIED: _ClassVar[PetSnapshotSecureFile.FileType]
        FILE_TYPE_PNG: _ClassVar[PetSnapshotSecureFile.FileType]
        FILE_TYPE_JPEG: _ClassVar[PetSnapshotSecureFile.FileType]
        FILE_TYPE_WEBP: _ClassVar[PetSnapshotSecureFile.FileType]
    FILE_TYPE_UNSPECIFIED: PetSnapshotSecureFile.FileType
    FILE_TYPE_PNG: PetSnapshotSecureFile.FileType
    FILE_TYPE_JPEG: PetSnapshotSecureFile.FileType
    FILE_TYPE_WEBP: PetSnapshotSecureFile.FileType
    class Metadata(_message.Message):
        __slots__ = ("file_type", "file_size", "created_at")
        FILE_TYPE_FIELD_NUMBER: _ClassVar[int]
        FILE_SIZE_FIELD_NUMBER: _ClassVar[int]
        CREATED_AT_FIELD_NUMBER: _ClassVar[int]
        file_type: PetSnapshotSecureFile.FileType
        file_size: int
        created_at: PetSnapshotSecureFile.CreatedAt
        def __init__(self, file_type: _Optional[_Union[PetSnapshotSecureFile.FileType, str]] = ..., file_size: _Optional[int] = ..., created_at: _Optional[_Union[PetSnapshotSecureFile.CreatedAt, _Mapping]] = ...) -> None: ...
    class CreatedAt(_message.Message):
        __slots__ = ("seconds",)
        SECONDS_FIELD_NUMBER: _ClassVar[int]
        seconds: int
        def __init__(self, seconds: _Optional[int] = ...) -> None: ...
    METADATA_FIELD_NUMBER: _ClassVar[int]
    metadata: PetSnapshotSecureFile.Metadata
    def __init__(self, metadata: _Optional[_Union[PetSnapshotSecureFile.Metadata, _Mapping]] = ...) -> None: ...
