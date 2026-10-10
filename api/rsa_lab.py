"""Bounded server-side RSA-OAEP teaching lab. Private keys never enter Wallet."""
import base64
import binascii
import hashlib
import re
import threading
import time
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from pydantic import BaseModel, Field, StrictStr, field_validator
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

from api.session_store import current_session

class RsaRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def validate(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                # Do not echo invalid Unicode or submitted PEM/text in errors.
                return JSONResponse(status_code=422, content={"detail": [
                    {"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in error.errors()]})
        return validate


router = APIRouter(prefix="/api/labs/rsa", tags=["rsa"], route_class=RsaRoute)
generation_slots = threading.BoundedSemaphore(2)
KEY_TTL = 900
KEY_LIMIT = 8
PURPOSE_LIMIT = 4
Handle = Annotated[StrictStr, Field(max_length=64, pattern=r"^[A-Za-z0-9_-]{22}\.[0-9a-f]{32}$")]


def oaep():
    return padding.OAEP(padding.MGF1(hashes.SHA256()), hashes.SHA256(), None)


def generate_rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_metadata(key):
    public = key.public_key() if isinstance(key, rsa.RSAPrivateKey) else key
    der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return {"public_key_pem": public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii"),
            "public_key_fingerprint": hashlib.sha256(der).hexdigest(), "key_size": 2048, "public_exponent": 65537}


def parse_public_key(pem):
    try:
        pem.encode("ascii")
        normalized = pem.replace("\r\n", "\n").strip()
        if re.fullmatch(r"-----BEGIN PUBLIC KEY-----\n[A-Za-z0-9+/=\s]+\n-----END PUBLIC KEY-----", normalized) is None:
            raise ValueError()
        key = serialization.load_pem_public_key(normalized.encode("ascii"))
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size != 2048 or key.public_numbers().e != 65537:
            raise ValueError()
        return key
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("Cần một public key RSA-2048/e65537 dạng PEM SubjectPublicKeyInfo")


def decode_artifact(value):
    try:
        data = base64.b64decode(value, validate=True)
        if len(data) != 256 or base64.b64encode(data).decode("ascii") != value:
            raise ValueError()
        return data
    except (ValueError, binascii.Error):
        raise ValueError("Ciphertext cần Base64 chuẩn có padding, đúng 256 byte, không khoảng trắng")


class StrictRequest(BaseModel):
    model_config = {"extra": "forbid"}


class KeyRequest(StrictRequest):
    purpose: Literal["oaep"]


class EncryptRequest(StrictRequest):
    message: StrictStr = Field(max_length=190)
    public_key_pem: StrictStr = Field(max_length=2048)

    @field_validator("message")
    @classmethod
    def text_bytes(cls, value):
        if len(value.encode("utf-8")) > 190:
            raise ValueError("RSA-OAEP tối đa 190 byte UTF-8")
        return value

    @field_validator("public_key_pem")
    @classmethod
    def public_key(cls, value):
        parse_public_key(value)
        return value


class DecryptRequest(StrictRequest):
    key_handle: Handle
    ciphertext_b64: StrictStr = Field(max_length=344)

    @field_validator("ciphertext_b64")
    @classmethod
    def ciphertext(cls, value):
        decode_artifact(value)
        return value


def encrypt_text(message, public_key):
    data = public_key.encrypt(message.encode("utf-8"), oaep())
    return {"outcome": {"code": "encrypted", "message": "Đã mã hóa bằng public key trên backend."},
            "scheme": "RSA-OAEP", "hash": "SHA-256", "mgf1_hash": "SHA-256", "label": None,
            "message": message, "message_utf8_bytes": len(message.encode("utf-8")),
            "key_size": 2048, "public_key_fingerprint": public_metadata(public_key)["public_key_fingerprint"],
            "ciphertext_b64": base64.b64encode(data).decode("ascii"), "ciphertext_bytes": len(data)}


def decrypt_text(ciphertext, private_key):
    try:
        raw = private_key.decrypt(ciphertext, oaep())
    except ValueError:
        return {"outcome": {"code": "decryption_failed", "message": "Không giải mã được với khóa và tham số đã chọn; có thể sai khóa hoặc dữ liệu bị thay đổi."},
                "decrypted": False, "plaintext": None, "plaintext_utf8_bytes": None}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"outcome": {"code": "plaintext_not_utf8", "message": "OAEP đã giải mã được byte, nhưng dữ liệu không phải văn bản UTF-8."},
                "decrypted": True, "plaintext": None, "plaintext_utf8_bytes": None}
    return {"outcome": {"code": "decrypted", "message": "Đã giải mã văn bản UTF-8 bằng private key trên backend."},
            "decrypted": True, "plaintext": text, "plaintext_utf8_bytes": len(raw)}


def expire_keys(context):
    # Like the ECDSA lab: unusable at TTL, lazily removed on key operations.
    now = time.monotonic()
    for handle, entry in list(context.rsa_keys.items()):
        if entry["expires"] <= now:
            del context.rsa_keys[handle]


def key_unavailable():
    raise HTTPException(404, detail={"code": "key_unavailable", "message": "Khóa riêng không khả dụng, đã hết hạn hoặc không thuộc phiên này."})


def owned_key(context, handle):
    expire_keys(context)
    entry = context.rsa_keys.get(handle)
    if not handle.startswith(context.rsa_owner + ".") or entry is None:
        key_unavailable()
    return entry


def key_response(handle, entry):
    return {**public_metadata(entry["private_key"]), "key_handle": handle, "purpose": entry["purpose"],
            "expires_in_seconds": max(0, int(entry["expires"] - time.monotonic()))}


@router.post("/keys", status_code=201)
def create_key(body: KeyRequest):
    context = current_session()
    if not context.rsa_generation_lock.acquire(False):
        raise HTTPException(429, detail={"code": "rsa_generation_busy", "message": "Phiên đang tạo khóa; hãy thử lại chủ động."})
    acquired = False
    try:
        acquired = generation_slots.acquire(False)
        if not acquired:
            raise HTTPException(429, detail={"code": "rsa_generation_busy", "message": "Backend đang tạo tối đa hai khóa; hãy thử lại sau."})
        with context.rsa_key_lock:
            expire_keys(context)
            if len(context.rsa_keys) >= KEY_LIMIT or sum(e["purpose"] == body.purpose for e in context.rsa_keys.values()) >= PURPOSE_LIMIT:
                raise HTTPException(429, detail={"code": "rsa_key_capacity", "message": "Đã đủ khóa RSA tạm; xóa khóa không dùng hoặc chờ hết hạn."})
        try:
            private = generate_rsa_key()
        except Exception:
            raise HTTPException(503, detail={"code": "rsa_generation_unavailable", "message": "Backend chưa tạo được khóa; không có khóa mới được publish."})
        with context.rsa_key_lock:
            if context.retiring:
                raise HTTPException(503, detail={"code": "rsa_generation_unavailable", "message": "Phiên đang đóng; không publish khóa mới."})
            handle = context.rsa_owner + "." + uuid.uuid4().hex
            entry = {"purpose": body.purpose, "private_key": private, "expires": time.monotonic() + KEY_TTL}
            response = key_response(handle, entry)
            context.rsa_keys[handle] = entry
            return response
    finally:
        if acquired:
            generation_slots.release()
        context.rsa_generation_lock.release()


@router.get("/keys/{key_handle}")
def get_key(key_handle: Handle):
    context = current_session()
    with context.rsa_key_lock:
        return key_response(key_handle, owned_key(context, key_handle))


@router.delete("/keys/{key_handle}")
def delete_key(key_handle: Handle):
    context = current_session()
    with context.rsa_key_lock:
        expire_keys(context)
        if not key_handle.startswith(context.rsa_owner + "."):
            key_unavailable()
        return {"cleared": context.rsa_keys.pop(key_handle, None) is not None}


@router.post("/encrypt")
def encrypt(body: EncryptRequest):
    try:
        return encrypt_text(body.message, parse_public_key(body.public_key_pem))
    except Exception:
        raise HTTPException(500, detail={"code": "rsa_operation_failed", "message": "Backend gặp lỗi vận hành khi mã hóa; chưa có kết quả đáng tin."})


@router.post("/decrypt")
def decrypt(body: DecryptRequest):
    context = current_session()
    with context.rsa_key_lock:
        entry = owned_key(context, body.key_handle)
        if entry["purpose"] != "oaep":
            raise HTTPException(409, detail={"code": "key_purpose_mismatch", "message": "Cần khóa dành cho RSA-OAEP."})
        try:
            result = decrypt_text(decode_artifact(body.ciphertext_b64), entry["private_key"])
        except Exception:
            raise HTTPException(500, detail={"code": "rsa_operation_failed", "message": "Backend gặp lỗi vận hành khi giải mã; chưa có kết quả đáng tin."})
        if entry["expires"] <= time.monotonic():
            expire_keys(context)
            key_unavailable()
        return {**result, "key_handle": body.key_handle, "public_key_fingerprint": public_metadata(entry["private_key"])["public_key_fingerprint"], "scheme": "RSA-OAEP"}
