# ===========================================================================
#  ccm_check.py - prueft die AES-CCM-Logik aus Sources/Core/Crypto.swift
#  (Zeile fuer Zeile nach Python portiert) gegen cryptography.AESCCM.
#  Zusaetzlich: CCM-Verschluesselung wie in Sources/Devices/Speedport.swift
#  und der Speedport-Fall (Nonce = key[:8], Tag 16) als Gegenprobe.
#  Autor: T. Pfeiffer
# ===========================================================================
import os
import random
import sys

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESCCM


def aes_ecb(key, block):
    e = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return e.update(block) + e.finalize()


def aes_cbc_nopad(key, iv, data):
    e = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return e.update(data) + e.finalize()


def aes_ctr(key, counter, data):
    # Port of Crypto.aesCTR
    ctr = bytearray(counter)
    out = bytearray()
    i = 0
    while i < len(data):
        ks = aes_ecb(key, bytes(ctr))
        n = min(16, len(data) - i)
        for k in range(n):
            out.append(data[i + k] ^ ks[k])
        i += n
        j = 15
        while j >= 0:
            ctr[j] = (ctr[j] + 1) & 0xFF
            if ctr[j] != 0:
                break
            j -= 1
    return bytes(out)


def swift_ccm_decrypt(key, nonce, ct_and_tag, aad=b"", tag_len=16):
    # Line-by-line port of Crypto.aesCCMDecrypt
    if len(ct_and_tag) < tag_len:
        raise ValueError("CCM: zu kurz")
    ct = ct_and_tag[:len(ct_and_tag) - tag_len]
    tag = ct_and_tag[len(ct_and_tag) - tag_len:]
    L = 15 - len(nonce)

    def ctr_block(i):
        b = bytes([L - 1]) + nonce
        tail = [0] * L
        v = i
        k = L - 1
        while k >= 0:
            tail[k] = v & 0xFF
            v >>= 8
            k -= 1
        return b + bytes(tail)

    s0 = aes_ecb(key, ctr_block(0))
    plain = aes_ctr(key, ctr_block(1), ct)
    flags = ((((tag_len - 2) // 2) << 3) & 0xFF) | (L - 1)
    if aad:
        flags |= 0x40
    b0 = bytes([flags]) + nonce
    ln = [0] * L
    v = len(plain)
    k = L - 1
    while k >= 0:
        ln[k] = v & 0xFF
        v >>= 8
        k -= 1
    b0 += bytes(ln)
    mac_input = b0
    if aad:
        a = bytearray()
        if len(aad) < 0xFF00:
            a.append((len(aad) >> 8) & 0xFF)
            a.append(len(aad) & 0xFF)
        else:
            a += bytes([0xFF, 0xFE])
            c = len(aad)
            a += bytes([c >> 24, (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF])
        a += aad
        while len(a) % 16 != 0:
            a.append(0)
        mac_input += bytes(a)
    p = bytearray(plain)
    while len(p) % 16 != 0:
        p.append(0)
    mac_input += bytes(p)
    mac = aes_cbc_nopad(key, bytes(16), mac_input)[-16:]
    t = bytes(mac[i] ^ s0[i] for i in range(tag_len))
    if t != tag:
        raise ValueError("CCM: Pruefsumme falsch")
    return plain


def swift_ccm_encrypt(key, nonce, plain, tag_len=16):
    # Port of SpeedportCCM.encrypt (no AAD) from Speedport.swift
    L = 15 - len(nonce)

    def ctr_block(i):
        b = bytearray([L - 1]) + nonce
        tail = [0] * L
        v = i
        k = L - 1
        while k >= 0:
            tail[k] = v & 0xFF
            v >>= 8
            k -= 1
        return bytes(b) + bytes(tail)

    flags = (((tag_len - 2) // 2) << 3) | (L - 1)
    b0 = bytearray([flags]) + nonce
    ln = [0] * L
    v = len(plain)
    k = L - 1
    while k >= 0:
        ln[k] = v & 0xFF
        v >>= 8
        k -= 1
    b0 += bytes(ln)
    p = bytearray(plain)
    while len(p) % 16 != 0:
        p.append(0)
    mac = aes_cbc_nopad(key, bytes(16), bytes(b0) + bytes(p))[-16:]
    s0 = aes_ecb(key, ctr_block(0))
    ct = aes_ctr(key, ctr_block(1), plain)
    tag = bytes(mac[i] ^ s0[i] for i in range(tag_len))
    return ct + tag


def main():
    rnd = random.Random(1234)
    ok = 0
    bad = 0
    cases = []
    for nlen in range(7, 14):
        for tag_len in (8, 16):
            for aad_len in (0, 1, 15, 16, 40):
                for plen in (0, 1, 15, 16, 17, 100, 333):
                    cases.append((nlen, tag_len, aad_len, plen))
    for nlen, tag_len, aad_len, plen in cases:
        key = os.urandom(rnd.choice((16, 24, 32)))
        nonce = os.urandom(nlen)
        aad = os.urandom(aad_len)
        pt = os.urandom(plen)
        ref = AESCCM(key, tag_length=tag_len).encrypt(nonce, pt, aad or None)
        try:
            got = swift_ccm_decrypt(key, nonce, ref, aad, tag_len)
            good = got == pt
        except Exception as exc:
            good = False
            print("FAIL decrypt", nlen, tag_len, aad_len, plen, exc)
        if not aad:
            enc = swift_ccm_encrypt(key, nonce, pt, tag_len)
            good = good and enc == ref
        # tampered tag must fail
        if ref:
            tam = bytearray(ref)
            tam[-1] ^= 1
            try:
                swift_ccm_decrypt(key, nonce, bytes(tam), aad, tag_len)
                good = False
                print("FAIL tamper accepted", nlen, tag_len, aad_len, plen)
            except ValueError:
                pass
        if good:
            ok += 1
        else:
            bad += 1
    # Speedport case: key = DEFAULT_KEY, nonce = key[:8], tag 16
    key = bytes.fromhex("cdc0cac1280b516e674f0057e4929bca84447cca8425007e33a88a5cf598a190")
    msg = b'[{"vartype":"status","varid":"onlinestatus","varvalue":"online"}]'
    ref = AESCCM(key, tag_length=16).encrypt(key[:8], msg, None)
    sp_ok = (swift_ccm_encrypt(key, key[:8], msg) == ref
             and swift_ccm_decrypt(key, key[:8], ref) == msg)
    print("Vektoren: %d ok, %d fehlerhaft" % (ok, bad))
    print("Speedport-Fall (Default-Key, Nonce key[:8], Tag 16): %s" % ("OK" if sp_ok else "FEHLER"))
    sys.exit(0 if bad == 0 and sp_ok else 1)


if __name__ == "__main__":
    main()
