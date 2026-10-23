from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder
from .proto import secure_file_transfer_pb2

_PET_SNAPSHOT_FILE_TYPE: Final[dict[int, str]] = {
    1: "image/png",
    2: "image/jpeg",
    3: "image/webp",
}


@RVMDecoder.register(
    secure_file_transfer_pb2.PetSnapshotSecureFile,
    "secure_file_transfer.pet_snapshot.secure_file",
)
def decode_pet_snapshot(
    m: secure_file_transfer_pb2.PetSnapshotSecureFile,
) -> dict[str, Any]:
    metadata = m.metadata
    snapshot: dict[str, Any] = {}
    if metadata.file_type in _PET_SNAPSHOT_FILE_TYPE:
        snapshot["fileType"] = _PET_SNAPSHOT_FILE_TYPE[metadata.file_type]
    if metadata.HasField("file_size"):
        snapshot["fileSize"] = metadata.file_size
    if metadata.created_at.HasField("seconds"):
        snapshot["createdAt"] = metadata.created_at.seconds
    return {"petSnapshot": snapshot} if snapshot else {}
