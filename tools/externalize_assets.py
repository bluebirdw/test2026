#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把三个 HTML 里内嵌的 base64 资源(data:image/* 与内嵌视频)提取成独立文件，并按内容哈希去重。

用法（在仓库根目录运行）：
    python3 tools/externalize_assets.py --dry-run   # 只看体积统计，不落盘
    python3 tools/externalize_assets.py             # 真正提取并改写 HTML

产物写入 assets/，HTML 中的 data URI 替换为相对路径（根目录写 assets/，m/ 与 cases/ 写 ../assets/）。
"""
import base64
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = [('index.html', ''), ('m/index.html', '../'), ('cases/index.html', '../')]
URI_RE = re.compile(r'data:([\w/+.\-]+);base64,([A-Za-z0-9+/=]+)')

# 按就近出现的上下文标记推断文件名前缀（取位置最靠后的那个标记）
MARKERS = [
    ('hero-video', 'hero'), ('member-photo', 'team'), ('team-card', 'team'), ('team-member', 'team'),
    ('work-media', 'work'), ('work-slide', 'work'), ('work-card', 'work'),
    ('gallery-slide', 'case'),
    ('brand-logo', 'brand'), ('brand-lockup', 'brand'),
    ('apple-touch-icon', 'touchicon'), ('rel="icon"', 'favicon'),
    ('member-school-seal', 'seal'), ('education-mark', 'seal'),
]


def sniff(raw):
    """按魔数判断真实类型（mime 有时是 application/octet-stream，实际是 mp4）"""
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return 'webp'
    if raw.startswith(b'\x89PNG'):
        return 'png'
    if raw.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if raw[:4] == b'\x1aE\xdf\xa3':
        return 'webm'
    if len(raw) > 12 and raw[4:8] == b'ftyp':
        return 'mp4'
    head = raw[:200].lstrip()
    if head.startswith(b'<svg') or head.startswith(b'<?xml'):
        return 'svg'
    return None


def prefix_for(text, pos, ext, raw):
    if ext == 'svg':
        return 'logo-anim' if b'<animate' in raw[:4000] else 'logo-still'
    if ext in ('mp4', 'webm'):
        return 'video'
    back = text[max(0, pos - 24):pos]
    if 'url("data:' in back or "url('data:" in back or back.rstrip().endswith('url("') \
            or back.rstrip().endswith("url('"):
        return 'bg'
    window = text[max(0, pos - 900):pos]
    best, best_pos = 'img', -1
    for token, pre in MARKERS:
        i = window.rfind(token)
        if i > best_pos:
            best_pos, best = i, pre
    return best


def main():
    dry = '--dry-run' in sys.argv
    assets_dir = os.path.join(ROOT, 'assets')
    if not dry:
        os.makedirs(assets_dir, exist_ok=True)
    by_hash, written = {}, []
    report = {p: {'before': 0, 'after': 0, 'refs': 0, 'bytes': 0} for p, _ in PAGES}
    for page, up in PAGES:
        path = os.path.join(ROOT, page)
        s = open(path, encoding='utf-8').read()
        report[page]['before'] = len(s)
        stats = {}

        def repl(m):
            mime, b64 = m.group(1), m.group(2)
            raw = base64.b64decode(b64)
            h = hashlib.sha1(raw).hexdigest()[:8]
            ext = sniff(raw) or {'image/webp': 'webp', 'image/png': 'png',
                                 'image/jpeg': 'jpg', 'image/svg+xml': 'svg'}.get(mime, 'bin')
            pre = prefix_for(s, m.start(), ext, raw)
            name = by_hash.get(h)
            if name is None:
                name = '%s-%s.%s' % (pre, h, ext)
                by_hash[h] = name
                written.append((name, len(raw)))
                if not dry:
                    with open(os.path.join(assets_dir, name), 'wb') as fh:
                        fh.write(raw)
            stats[pre] = stats.get(pre, 0) + 1
            report[page]['refs'] += 1
            report[page]['bytes'] += len(raw)
            return '%sassets/%s' % (up, name)

        s2 = URI_RE.sub(repl, s)
        report[page]['after'] = len(s2)
        report[page]['stats'] = stats
        if not dry:
            open(path, 'w', encoding='utf-8').write(s2)

    total_asset = sum(n for _, n in written)
    print('%s提取资源 %d 个，合计 %.2f MB' % ('[dry-run] ' if dry else '', len(written), total_asset / 1048576))
    for page, r in report.items():
        print('  %-18s %7.2f MB -> %5.2f MB  (引用 %d 处 / 原始 %.2f MB)  类型 %s'
              % (page, r['before'] / 1048576, r['after'] / 1048576,
                 r['refs'], r['bytes'] / 1048576, r['stats']))
    print('去重节省：%.2f MB' % ((sum(r['bytes'] for r in report.values()) - total_asset) / 1048576))


if __name__ == '__main__':
    main()
