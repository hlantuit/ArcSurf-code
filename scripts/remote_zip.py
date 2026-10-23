"""List or extract members of a large remote zip without downloading all of it (HTTP Range requests; OSTR bitstreams
answer 206). zipfile reads the (ZIP64) central directory and the chosen members through a seekable HTTP file object.
usage: remote_zip.py <url> list [regex]
       remote_zip.py <url> extract <regex> <outdir>      (members whose path matches regex, case-insensitive)"""
import io
import os
import re
import sys
import urllib.request
import zipfile

UA = 'AWI-research/1.0 (+https://www.awi.de)'


class HttpFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos, self.fetched = url, 0, 0
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            self.size = int(r.headers['Content-Length'])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b''
        end = min(self.size, self.pos + n) - 1
        req = urllib.request.Request(self.url, headers={'User-Agent': UA, 'Range': f'bytes={self.pos}-{end}'})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    data = r.read()
                break
            except Exception:
                if attempt == 4:
                    raise
        self.pos += len(data)
        self.fetched += len(data)
        return data

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


if __name__ == '__main__':
    url, mode = sys.argv[1], sys.argv[2]
    f = io.BufferedReader(HttpFile(url), buffer_size=1 << 20)
    z = zipfile.ZipFile(f)
    infos = z.infolist()
    if mode == 'list':
        pat = re.compile(sys.argv[3], re.I) if len(sys.argv) > 3 else None
        for i in infos:
            if pat is None or pat.search(i.filename):
                print(f'{i.file_size / 1e6:10.1f} MB ({i.compress_size / 1e6:.1f} zipped)  {i.filename}')
        print(len(infos), 'members,', round(sum(i.file_size for i in infos) / 1e6), 'MB uncompressed')
    else:
        pat, out = re.compile(sys.argv[3], re.I), sys.argv[4]
        n = 0
        for i in infos:
            if pat.search(i.filename) and not i.is_dir():
                dst = os.path.join(out, i.filename)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(i) as src, open(dst, 'wb') as fh:
                    while True:
                        b = src.read(1 << 22)
                        if not b:
                            break
                        fh.write(b)
                n += 1
                print('extracted', i.filename, round(i.file_size / 1e6, 1), 'MB')
        print(n, 'members extracted; downloaded', round(f.raw.fetched / 1e6, 1), 'MB of', round(f.raw.size / 1e6), 'MB')
