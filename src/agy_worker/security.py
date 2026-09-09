"""Windows data_dir ACL advisory；只诊断，不自动修改权限。"""
from pathlib import Path

# Windows access-mask bits used by the advisory. FILE_READ_DATA is also
# FILE_LIST_DIRECTORY for directories.
FILE_READ_DATA = 0x00000001
GENERIC_READ = 0x80000000
GENERIC_ALL = 0x10000000

# 这些主体代表“同机其他普通身份可能广泛读取”的典型风险面。
_BROAD_READ_SIDS = {
    "S-1-1-0",       # Everyone
    "S-1-5-11",      # Authenticated Users
    "S-1-5-32-545",  # BUILTIN\\Users
    "S-1-5-32-546",  # BUILTIN\\Guests
}


def _grants_read(access_mask):
    return bool(access_mask & (FILE_READ_DATA | GENERIC_READ | GENERIC_ALL))


def classify_broad_read_principals(entries):
    """从归一化 ACE 列表中找出显式宽泛读取 grant，保持首次出现顺序。"""
    result = []
    seen = set()
    for entry in entries:
        if not entry.get("allowed") or not _grants_read(int(entry.get("access_mask", 0))):
            continue
        sid = str(entry.get("sid", ""))
        if sid not in _BROAD_READ_SIDS:
            continue
        principal = str(entry.get("principal") or sid)
        if principal not in seen:
            seen.add(principal)
            result.append(principal)
    return result


def _read_acl_entries(path):
    """读取 Windows DACL，并转换成不依赖 pywin32 对象的最小结构。"""
    import win32security

    descriptor = win32security.GetFileSecurity(
        str(Path(path)), win32security.DACL_SECURITY_INFORMATION
    )
    dacl = descriptor.GetSecurityDescriptorDacl()
    if dacl is None:
        # NULL DACL 代表完全开放；用 Everyone 的 broad-read grant 表示风险。
        return [{
            "sid": "S-1-1-0",
            "principal": "Everyone",
            "access_mask": GENERIC_ALL,
            "allowed": True,
        }]

    allow_types = {
        win32security.ACCESS_ALLOWED_ACE_TYPE,
        getattr(win32security, "ACCESS_ALLOWED_OBJECT_ACE_TYPE", -1),
        getattr(win32security, "ACCESS_ALLOWED_CALLBACK_ACE_TYPE", -1),
        getattr(win32security, "ACCESS_ALLOWED_CALLBACK_OBJECT_ACE_TYPE", -1),
    }
    entries = []
    for index in range(dacl.GetAceCount()):
        ace = dacl.GetAce(index)
        header = ace[0]
        ace_type = header[0]
        access_mask = ace[1]
        sid = ace[-1]
        sid_text = win32security.ConvertSidToStringSid(sid)
        try:
            name, domain, _sid_type = win32security.LookupAccountSid(None, sid)
            principal = f"{domain}\\{name}" if domain else name
        except Exception:
            principal = sid_text
        entries.append({
            "sid": sid_text,
            "principal": principal,
            "access_mask": int(access_mask),
            "allowed": ace_type in allow_types,
        })
    return entries


def inspect_data_dir_acl(path):
    """返回凭据目录 ACL advisory；检查失败保持 unknown，不把未知当安全。"""
    try:
        entries = _read_acl_entries(Path(path))
        broad = classify_broad_read_principals(entries)
        return {
            "checked": True,
            "broad_read_principals": broad,
            # True 表示发现会削弱 controller token 保密性的宽泛读取 grant。
            "token_confidentiality_advisory": bool(broad),
        }
    except Exception as error:
        return {
            "checked": False,
            "broad_read_principals": [],
            "token_confidentiality_advisory": False,
            "error": str(error)[:1000],
        }
