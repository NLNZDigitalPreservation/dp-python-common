from pathlib import Path

import requests


def _is_verified(args):
    if args.auth_mode == "azurite":
        return False

    # if args.managed_identity_client_id:
    #     return True

    # return False
    return args.fixity_ssl_verify


def _request(method, args, url, json=None, headers=None):
    host_key = args.fixity_worker_func_hosts_key
    req_headers = dict(headers or {})

    if host_key:
        req_headers["x-functions-key"] = host_key

    is_verified = _is_verified(args)
    req_kwargs = {
        "json": json,
        "headers": req_headers or None,
        "verify": is_verified,
    }

    # Keep backward compatibility with the legacy fixity_ssl_cert field while
    # also supporting the current fixity_ca_bundle location setting.
    cert_base_dir = getattr(args, "fixity_ssl_cert", None) or getattr(
        args, "fixity_ca_bundle", None
    )
    if cert_base_dir:
        cert_path = Path(cert_base_dir) / "fixity.cer"
        key_path = Path(cert_base_dir) / "fixity.key"
        if cert_path.is_file() and key_path.is_file():
            req_kwargs["cert"] = (str(cert_path), str(key_path))

    rsp = requests.request(
        method,
        url,
        **req_kwargs,
    )
    return rsp


def get(args, url, headers=None):
    response = _request("GET", args, url, headers=headers)
    return response


def post(args, url, json):
    response = _request("POST", args, url, json=json)
    return response


def delete(args, url, json=None):
    response = _request("DELETE", args, url, json=json)
    return response
