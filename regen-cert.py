# -*- coding: utf-8 -*-
"""
重新生成自签名 HTTPS 证书（cert.pem / key.pem）。

什么时候需要：
  - 新电脑部署时不想用打包里自带的旧证书；
  - 手机浏览器提示证书异常、想换一对新的。

用法：
  .venv\\Scripts\\python.exe regen-cert.py
"""
import datetime
import os
import sys

try:
    from OpenSSL import crypto
except ImportError:
    print("缺少 pyopenssl，请先执行: pip install pyopenssl")
    sys.exit(1)


def main():
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)

    cert = crypto.X509()
    cert.set_version(2)
    cert.get_subject().CN = "Movo"
    cert.set_serial_number(int(datetime.datetime.now().timestamp()))
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)  # 10 年
    cert.set_issuer(cert.get_subject())  # 自签名
    cert.set_pubkey(key)
    cert.add_extensions([
        crypto.X509Extension(b"subjectAltName", False,
                             b"DNS:localhost,IP:127.0.0.1"),
        crypto.X509Extension(b"basicConstraints", True, b"CA:false"),
        crypto.X509Extension(b"keyUsage", True,
                             b"digitalSignature,keyEncipherment"),
    ])
    cert.sign(key, "sha256")

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "cert.pem"), "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    with open(os.path.join(here, "key.pem"), "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))

    print("OK: cert.pem / key.pem 已重新生成（有效期 10 年）")


if __name__ == "__main__":
    main()
