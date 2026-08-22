# Gen 2 (PRE_CCC) BLE pairing — APK ground truth vs. this repo

Read-only analysis. Component 1 (`apk-ground-truth`) of
`.omc/specs/deep-interview-gen2-ble-control-chain.md`. **No code was changed.**

APK: `com.rivian.android.consumer/java_src/`. All claims below carry a file:line anchor.
Anything not proven from the APK is labelled UNPROVEN rather than guessed.

---

## Headline

**The Gen 2 VAS wire format is not Protocol Buffers.** It is fixed-size little-endian
`ByteBuffer` framing. `ble_gen2_proto.py` — the whole hand-rolled protobuf encoder and parser —
is modelling a protocol that does not exist.

**And the Gen 2 crypto is the same crypto Gen 1 already implements correctly in this repo.**
`ble_gen2.py` reimplemented key derivation from scratch and dropped the HKDF step that
`utils.py:93-99` — thirty lines away, on the working Gen 1 path — already had right. Every
Gen 2 HMAC is therefore computed under the wrong key, which alone guarantees pairing failure
regardless of framing.

The Gen 2 pairing frame is **byte-for-byte identical in construction to the Gen 1 frame that
works today**. The implementation invented a different protocol than the one the app speaks.

---

## The actual Gen 2 protocol

### Key derivation — `C15277l.java:908-949`

```
Z   = ECDH(phone_private_key, vehicle_public_key)        # prime256v1 / P-256
key = HKDF-SHA256(ikm=Z, salt=None, info=b"", L=32)
```

- `KeyAgreement.getInstance("ECDH", BouncyCastle)`, `ECGenParameterSpec("prime256v1")` — `:912,921`
- Vehicle public key validated as 65 bytes, first byte `0x04` — `:927-930`
- KDF params `C10059N` = `HKDFParameters(ikm, salt=null, info=new byte[0])` —
  `p576Xm/C10059N.java:13-19`
- Generator identified by its own error string: `"HKDF parameters required for
  HKDFBytesGenerator"` — `p010A8/C0116w.java:419`
- Digest is SHA-256 — `C5017y.java:193-194` (`getAlgorithmName() → "SHA-256"`)
- MAC is `HMac(SHA-256)` — `C15277l.java:266-275`
- `m7873d(userId, vehiclePublicKey, …)` validates `len==130` and `startsWith("04")` —
  `fj/AbstractC14833a.java:96-99`

`userId` is a **keystore alias** used to fetch the phone's private key
(`c6104a.m17513a(label)`, `C15277l.java:915`), *not* key material. Passing a PEM private key
directly, as this repo does, is equivalent.

### Frame construction — `p616Ze/AbstractC10624g.java:1157-1219`

Type→branch mapping from `p638aj/AbstractC11132L.java:12-20`:
`AUTH_PNONCE→1`, `ACTIVE_COMMAND→2`, `PASSIVE_ENTRY→3`.

**AUTH_PNONCE (pairing) — `:1160-1169`, 48 bytes**

```
pNonce(16) || HMAC-SHA256(key, pNonce)(32)
```

The buffer is allocated `new byte[48]` — `:1161`. Note what is **absent**: no CSN, no phoneId,
no vehicleId. Those fields exist on the `C11131K` object but branch 1 never serializes them,
which is why the constructor at `C11162i.java:1167` passes CSN `-1` — a sentinel, not a value.

**ACTIVE_COMMAND — `:1174-1190`, `len(payload) + 32` bytes**

```
payload || HMAC-SHA256(key, pNonce(16) || vNonce(16) || csn(int32 LE) || payload)
```

HMAC input buffer allocated `new byte[payload.length + 36]` — `:1182`. 16+16+4 = 36 confirms
both nonces are exactly 16 bytes.

**PASSIVE_ENTRY — `:1191-1218`**

```
(csn(int32 LE) || payload) || HMAC-SHA256(key, pNonce || vNonce || csn(int32 LE) || payload)
```

### `m7360r()` is a no-op — `AbstractC15367g.java:322-329`

```java
ByteBuffer.wrap(bArr).order(LITTLE_ENDIAN).array()
```

`order()` affects multi-byte accessors, not `array()`, which returns the same backing array.
The wrapper is dead code **in the app itself**. Do not implement a byte reversal — there isn't
one. Endianness matters only for the `putInt(csn)` calls, which are genuinely little-endian.

### Response parsing — `p617Zf/AbstractC10629c.java:246-263`

`C11135O` is `VasResponse(type, payload, hmac)` — `p638aj/C11135O.java:19`.
Splits are plain `copyOfRange`:

| Type | payload | hmac | Anchor |
|---|---|---|---|
| `AUTH_VNONCE` | `bytes[0:16]` | `bytes[16:]` | `:262` |
| `ACTIVE_COMMAND` | `bytes[0:5]` | `bytes[5:]` | `:260` |
| `VEHICLE_STATUS` | `bytes[0:len-32]` | `bytes[len-32:]` | `:258` |
| `VEHICLE_MESSAGE` | `bytes[0:2]` | `bytes[2:4]` | `:254` |

So the pairing response is **48 bytes: `vNonce(16) || HMAC(32)`**.

### vNonce verification — `C11162i.java:1302-1314`

```java
order2 = ByteBuffer.wrap(new byte[32]).order(LITTLE_ENDIAN);
order2.put(pNonce);                        // 16
order2.put(resp.payload);                  // vNonce, 16
equals(resp.hmac, m7875b(order2.array()))  // HMAC-SHA256(key, pNonce || vNonce)
```

The phone **must** verify `HMAC(key, pNonce || vNonce)` against the returned HMAC. Failure
raises `NONCE_VERIFICATION_FAILURE` (`:1332`); the log string at `:1355` reads *"vnonce HMAC
check failed"*. The 32-byte allocation independently re-confirms 16-byte nonces.

> **Caveat, stated rather than glossed:** JADX renders the branch immediately after `equals4`
> incoherently (`:1329-1333` puts `NONCE_VERIFICATION_FAILURE` inside the success arm). The
> `Arrays.equals` comparison and the HMAC input are unambiguous; the surrounding control flow
> is a decompiler artifact and I have not reconstructed it. This does not affect the frame
> layout or the HMAC definition.

---

## Currency of this document

This is the **component-1 analysis, dated to the pre-rewrite tree**. The "Our code"
column below describes the implementation as it was FOUND, not as it now stands: the
subsequent rewrite (`s20`) implements deltas 1-8 and 10. Delta **#9 (vehicle-ID
validation inside the VAS flow) is deliberately NOT implemented** — the APK gives line
numbers but no byte-level format, and inventing a wire format is the exact mistake that
produced this whole defect. The UNPROVEN section near the end remains current: nothing
in the rewrite could close those, and only a real Gen 2 capture will.

## Delta table — every divergence found

| # | Area | Our code | APK ground truth | Severity |
|---|---|---|---|---|
| 1 | **Key derivation** | `ble_gen2.py:145` returns raw ECDH output — *"already 32 bytes for P-256"* | `HKDF-SHA256(Z, salt=None, info=b"", L=32)` — `C15277l.java:941-947` | **Fatal.** Wrong key ⇒ every HMAC wrong |
| 2 | **Wire format** | hand-rolled protobuf, `ble_gen2_proto.py` entire | fixed-size LE `ByteBuffer` — `AbstractC10624g.java:1157` | **Fatal.** Wrong protocol |
| 3 | **Pairing frame** | protobuf `{csn, {phone_id}, {phone_nonce}}` | `pNonce(16) ‖ HMAC(key,pNonce)(32)`, 48B — `:1160-1169` | **Fatal** |
| 4 | **HMAC input** | `protobuf ‖ csn(BE32) ‖ phoneId(16) ‖ pNonce(16) ‖ vNonce` — `ble_gen2_proto.py:214-222` | `pNonce ‖ vNonce ‖ csn(LE32) ‖ payload` — `:1181-1186`. Order, endianness and membership all differ; `phoneId` is **not** in the APK's input | **Fatal** |
| 5 | **CSN** | starts 1, `+= 2` | `-1` sentinel for AUTH_PNONCE; not serialized at all in that branch — `C11162i.java:1167` | **Fatal** |
| 6 | **vNonce verification** | absent — accepts any non-empty response (`ble_gen2.py:311`) | mandatory `HMAC(key, pNonce‖vNonce)` — `:1302-1314` | **Fatal + security** |
| 7 | **Response parse** | protobuf varint walk, `tag_byte = message[pos]` single byte | `bytes[0:16]` / `bytes[16:]` — `AbstractC10629c.java:262` | **Fatal** |
| 8 | **Bonding** | never triggered on Gen 2 path | Gen 1 path does `client.pair()` / Darwin notify (`ble.py:253-259`) | High |
| 9 | **Vehicle ID** | *"simplified here"*, skipped (`ble_gen2.py:277`) | validated — `C11162i.java:1727,1765,1776` | High |
| 10 | **Notifications** | subscribes `ENCRYPTED_DATA_OUT` only; `PLAIN_DATA_OUT` never subscribed | UNPROVEN — see below | Unknown |
| 11 | **Auth state machine** | `AuthState` 4 states | `EnumC11122B.java:12-15` | ✅ **Correct** |
| 12 | **Pubkey validation** | 130 hex chars, `"04"` prefix | `AbstractC14833a.java:96-99` | ✅ **Correct** |

---

## Gen 1 vs Gen 2 control chain (D2)

**They use the same crypto. The divergence is confined to pairing transport.**

| | Gen 1 | Gen 2 |
|---|---|---|
| Key | `HKDF-SHA256(ECDH, salt=None, info=b"")` — `utils.py:93-99` | identical — `C15277l.java:941-947` |
| Pairing frame | `phone_nonce ‖ HMAC(key, phone_nonce)` = 48B — `ble.py:243-249` | `pNonce ‖ HMAC(key, pNonce)` = 48B — `AbstractC10624g.java:1160-1169` |
| Characteristics | `AA49565A-…`, `E020A15D-…`, `5249565F-…` | `0823DA14-…`, `29919A3C-…`, `9A69AEFF-…`, `5EAA65C0-…` |
| vNonce HMAC check | not performed | **required** |
| Vehicle-ID exchange | own characteristic, compared to `vas_vehicle_id` | folded into the VAS flow |

**The Gen 1 and Gen 2 pairing frames are byte-for-byte identical in construction.** Gen 1's
`generate_ble_command_hmac(phone_nonce, vehicle_key, private_key)` (`utils.py:71-76`) computes
exactly what `AbstractC10624g.java:1166` computes.

### Post-pairing commands are generation-independent

The integration **never sends commands over BLE**. Grepping `write_gatt_char` across
`rivian_client/` returns only `ble.py:230,248` and `ble_gen2.py:238,297` — all pairing. Commands
go through the cloud via `generate_vehicle_command_hmac(command, timestamp, …)`
(`utils.py:79-85`), which signs `command+timestamp` with the *same* HKDF-derived key, and
`coordinator.py:1998-2007` / `:2043-2053` draw the same enrolled-phone material regardless of
generation.

The APK's `ACTIVE_COMMAND` / `PASSIVE_ENTRY` branches are the app's **BLE** command path — used
for passive entry and proximity unlock, which this integration does not implement.

**Conclusion for D2: fixing pairing is sufficient.** Once a Gen 2 phone key is correctly bonded,
the existing cloud control path should work unmodified. This narrows the scope you approved in
Round 4 — the "whole control chain" audit you asked for has been done, and it found the chain
downstream of pairing is already generation-agnostic. It does not need touching.

---

## What remains UNPROVEN

1. **Which characteristic the pairing frame is written to.** `C11162i.java:1173` writes via
   `c11169p2.m12517i(uuid6, uuid7, …)`; I did not resolve `uuid6`/`uuid7` to constants.
   `PLAIN_DATA_IN` is plausible but unconfirmed. **This is the top remaining unknown.**
2. **Whether responses arrive on `PLAIN_DATA_OUT` or `ENCRYPTED_DATA_OUT`.** An AES-128/GCM key
   is derived at `AbstractC14833a.java:77` (`SecretKeySpec(HMAC(f50307b)[0:16],
   "AES_128/GCM/NoPadding")`), so an encrypted channel exists — but whether the *pairing*
   handshake uses it, or only post-auth traffic, is unresolved. Our code subscribes only to
   `ENCRYPTED_DATA_OUT` and never to `PLAIN_DATA_OUT`; given the handshake frames are plainly
   MAC'd rather than encrypted, that looks wrong, but I have not proven it.
3. **MTU / fragmentation.** 48-byte frames fit a default 23-byte MTU only if the stack
   negotiates up. No evidence gathered.
4. **Where bonding is triggered** in the Gen 2 flow.
5. **The four Gen 2 characteristic UUIDs themselves** — inherited from the existing code, not
   re-derived from the APK in this pass.

Items 1, 2 and 5 are exactly what a tester's GATT-discovery dump plus frame trace would settle —
which is the `beta-enablement` component, and the reason D5 asked for the discovery dump.
`detect_vehicle_generation()` (`ble.py:88-125`) already enumerates every characteristic and
discards the list.

---

## Impact on the approved plan

- **`ble_gen2_proto.py` is not fixable — it should be deleted.** It models a protocol that does
  not exist. The replacement is well under 50 lines: two `struct.pack` frames, two slices, one
  `hmac.compare_digest`.
- **`ble_gen2.py` needs its crypto replaced with a call to the existing `utils.get_secret_key`.**
  Reimplementing it was the root cause of delta #1.
- **All 9 tests in `tests/client/test_ble_gen2.py` are testing the wrong protocol** and must be
  replaced, not repaired. `test_protobuf_phone_id_nonce_message` asserts `message[0] == 0x08` —
  a protobuf tag byte that will never appear on the wire.
- **The job got smaller, not bigger.** The framing risk flagged in the spec resolved in the
  favourable direction: the real protocol is far simpler than the invented one, and its crypto
  is already implemented and field-proven on the Gen 1 path.
