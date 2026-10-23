# Gen 2 (PRE_CCC) phone-key pairing — the verified protocol

Source: [walthowd/rivian-gen2-key-poc](https://github.com/walthowd/rivian-gen2-key-poc)
(MIT), tested on a 2026 R1S, with message layouts confirmed byte-for-byte against an
over-the-air capture of the official Android app pairing. `ble_gen2.py` ports its
`protocol.py`; `tests/client/test_ble_gen2.py` pins the captured sizes, and the builders
were cross-checked byte-identical to the PoC's over 2,000 random inputs.

This supersedes the static-analysis attempt in [GEN2_BLE_DELTA.md](GEN2_BLE_DELTA.md).
See [the scorecard](#scorecard-what-the-apk-analysis-got-right-and-wrong) at the end.

## Identifiers and key

| Name | Source | Use |
|---|---|---|
| phone key pair | generated locally (P-256) | public key sent in `enrollPhone` |
| `vasPhoneId` | `enrolledPhones[].vas.vasPhoneId` | phone id in BLE frames |
| `vasVehicleId` | `vehicles[].vas.vasVehicleId` | vehicle id in BLE frames **and the vehicle's advertised service UUID** |
| `vehiclePublicKey` | `vehicles[].vas.vehiclePublicKey` | ECDH peer |

```
key = HKDF-SHA256(ikm = ECDH(phone_private, vehicle_public), salt = None, info = b"", L = 32)
```

The same key signs cloud commands (`HMAC-SHA256(key, command || unix_timestamp)`), so
`utils.get_secret_key` serves Gen 1, Gen 2 and the cloud path alike.

## Advertising

The vehicle advertises `vasVehicleId` as a 128-bit service UUID with **no local name**,
from a resolvable private address that rotates (including when Set Up opens or times out).
Find it by UUID, never by name or address. Gen 1's "Rivian Phone Key" name does not exist
on Gen 2.

## GATT

Service `72cddca3-ab00-4e94-bae5-868f93f8c6c0` (usable only in Set Up or once bonded):

| | UUID | Props | Role | In `ble.py` |
|---|---|---|---|---|
| — | `1eb74dc8-3c1c-45ab-9254-9f41596cd4d6` | read, write | unused | — |
| **Q** | `0823da14-040b-4914-bf7c-450afa2850da` | write | phone → vehicle, plain | `GEN2_PLAIN_DATA_IN_UUID` |
| **R** | `29919a3c-a697-4a6f-bd3b-d14860cc9bce` | read, notify, indicate | vehicle → phone, plain | `GEN2_PLAIN_DATA_OUT_UUID` |
| S | `9a69aeff-e3fe-4e79-bb7d-5ae12272fd14` | write | phone → vehicle, encrypted link only | — |
| **T** | `5eaa65c0-57ee-4cf4-a3d5-a4aae20cbb0b` | read, notify, indicate | vehicle → phone, encrypted link only | `GEN2_ENCRYPTED_DATA_OUT_UUID` |

Also present: `0xFFF5` (CCC Digital Key) and an L2CAP CoC on PSM `0xCC`, both for wallet
keys, not this path.

## Messages (protobuf, field numbers only)

```
Envelope    { 2: Signed }
Signed      { 1: MessageList, 2: seq (uint32), 3: excludes_phone_nonce, 4: excludes_vehicle_nonce, 5: Signature }
Signature   { 1: algorithm (1 = HMAC-SHA256), 2: mac (32) }
MessageList { 1: Message (repeated) }
Message     { 1: transaction_id, 5: Auth | 9: ClientInfo }
Auth        { 1: Credentials }
Credentials { 1: id (16), 2: nonce (16) }
ClientInfo  { 1: Device { 2: model (string) } }

mac = HMAC-SHA256(key, MessageList || seq (u32 LE) || sender_id (16) || phone_nonce || vehicle_nonce)
```

| Step | Char | Content | seq | Sender | Nonces in MAC |
|---|---|---|---|---|---|
| auth#1 | Q | txn 1, `Auth{phone_id, pNonce}`; `Signed.4 = 1` | 1 | phone_id | pNonce |
| reply | R | `Auth{vasVehicleId, vNonce}` | vehicle's | vasVehicleId | both |
| auth#2 | Q | txn 3 `Auth{}` + txn 5 `ClientInfo{model}` | 2 | phone_id | both |

auth#1 is 90 bytes; auth#2 is 62 + len(model). The phone must verify the reply (vehicle id
and MAC over both nonces) before sending auth#2. An unsigned or wrongly signed auth#1 makes
the vehicle disconnect. Nothing answers auth#2.

## Bonding

Subscribing to T after auth#2 fails with ATT `0x05` (insufficient authentication), as it
does for the official app. The central then runs SMP; the vehicle answers with
NoInputNoOutput / Bonding+SC without MITM, so the result is LE Secure Connections
"Just Works". Two conditions:

1. The central must distribute its **IRK**, or the vehicle disconnects on the pairing request.
2. The central must accept Just Works (not insist on MITM).

Once encrypted, the T subscribe succeeds and the vehicle reports the key as paired to the
cloud by itself. No extra cloud call.

## What this means for Home Assistant

`ble_gen2.pair_phone_gen2` runs exactly that sequence. Whether HA can complete it depends on
the Bluetooth path, and none of these has been tested on a vehicle yet:

- **Local BlueZ adapter (HAOS, most installs): expected to fail.** The vehicle answers BlueZ's
  Service Changed CCCD write with ATT `0x03`; BlueZ then abandons its GATT client while still
  reporting services resolved, so bleak sees no services and `detect_vehicle_generation`
  returns 0 (it now logs why). Even past that, BlueZ only distributes an IRK with adapter
  privacy on and adds MITM unless the agent is NoInputNoOutput. A small BlueZ change (ignore
  that refusal) would remove the first obstacle.
- **ESPHome Bluetooth proxy: unknown.** It has its own GATT client, so the Service Changed
  quirk may not apply, and `pair()` is supported. Whether its SMP settings meet the two
  conditions above is untested.
- **macOS: works** (that is the PoC's primary platform), but HA does not run there.

### Workaround that does not need HA's Bluetooth

The bond is between the vehicle and whichever computer paired; cloud commands only need the
key to be marked paired. So HA's own key can be paired from a Mac:

1. Turn on *Vehicle control* in the integration's options (this enrolls HA's key).
2. Copy `/config/.storage/core.config_entries` to a Mac.
3. In the PoC: `python rivian_key.py import-ha core.config_entries`, then `python pair.py`.

HA enrolls its key with device type `"HA"`, not `"phone"`. The PoC flags this path as
experimental for that reason; please report results.

## Beyond pairing (from the PoC, not implemented here)

- Gen 2 honk/flash: `ACTIVATE_EXTERNAL_SOUND` and `FLASH_EXTERNAL_LIGHTS` work;
  `HONK_AND_FLASH_LIGHTS` is refused with `CONFLICT/VEHICLE_COMMAND_ERROR` (matches what
  this repo recorded in s19).
- Signed Parallax operations (`sendParallaxPayload`): payload field 17 =
  `{1: {1: 1, 2: HMAC-SHA256(key, command bytes)}, 2: identityId}`. The cloud returns
  success for unsigned payloads too, but the vehicle only acts on signed ones. Verified for
  Gear Guard (`security.video_monitoring.enable/disable_video_monitoring`), panic alarm
  (`security.alarm.enable/disable_panic`), Gear Guard live streaming and the Halloween
  costume. [PARALLAX_SEND_PATH.md](PARALLAX_SEND_PATH.md) concluded this envelope was
  "NOT DERIVABLE" from the APK.

## Scorecard: what the APK analysis got right and wrong

Two attempts exist: the original protobuf implementation (`ble_gen2_proto.py`, deleted in
s20) and the s20 rewrite based on [GEN2_BLE_DELTA.md](GEN2_BLE_DELTA.md).

**Right**

- The four characteristic UUIDs (Q, R, S, T) and the Gen 1 vs Gen 2 fingerprint (Q + T).
- Key derivation: HKDF-SHA256 over ECDH, no salt, empty info, the same as Gen 1 (s20 fixed
  the original's missing HKDF; that fix was correct).
- Cloud commands are generation-independent and need no change once the key is paired.
- The vehicle's reply must be verified before continuing, and pairing must fail closed.
- Bonding is required after the handshake.
- Public key validation (65 bytes / 130 hex, `04` prefix).

**Wrong**

| Claim | Reality |
|---|---|
| "The Gen 2 VAS wire format is not Protocol Buffers" (s20 headline) | It is protobuf. The deleted original was closer. |
| Pairing frame is `pNonce(16) ‖ HMAC(key, pNonce)` = 48 bytes, no phone id | 90-byte signed envelope carrying phone id and pNonce |
| Reply is `vNonce(16) ‖ HMAC(32)` = 48 bytes | Signed envelope carrying `vasVehicleId` and vNonce |
| MAC input `pNonce ‖ vNonce` (s20) | `MessageList ‖ seq LE32 ‖ sender_id ‖ pNonce ‖ vNonce?` |
| Phone id is not in the MAC input (s20 delta #4) | It is, as `sender_id` (the original had this right) |
| CSN is a big-endian field (original) / a `-1` sentinel (s20) | seq is little-endian u32: 1 then 2. Transaction ids go 1, 3, 5 (the original's "+2" was the transaction id) |
| One request/response; `SIGNED_PARAMS_SENT` never entered | Two writes: auth#1, then auth#2 with ClientInfo |
| Vehicle-ID validation format unknown (delta #9) | The reply's `Credentials.id` is `vasVehicleId`; checked in the MAC |
| Response arrives on plain or encrypted OUT, unknown | Reply on R (plain); T is subscribed only to trigger bonding |
| Bond via `client.pair()` / passive on Darwin, before or without T | Subscribe T, get ATT `0x05`, bond (Just Works + IRK), resubscribe |
| Find the vehicle by local name "Rivian Phone Key" | Gen 2 has no name; it advertises `vasVehicleId` as a service UUID |
| BlueZ is a viable pairing path | BlueZ hides all services (Service Changed quirk) and needs privacy + NoInputNoOutput |
| Signed Parallax envelope "NOT DERIVABLE" | Field 17: HMAC over the command bytes plus `identityId` |

The lesson the s20 write-up drew ("inventing a wire format is the mistake") was right in
spirit, but it then treated an unresolved decompiler path as ground truth. A guess, not
verified: the `ByteBuffer` framing it decoded is the app's Gen 1 / post-auth VAS framing,
not the Gen 2 pairing handshake.
