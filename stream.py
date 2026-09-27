MAX_FRAME = 4 * 1024 * 1024

def jpeg_frames(response):
    """Parse bounded multipart headers and complete JPEG payloads, including short reads."""
    while True:
        line = response.readline(4097)
        if not line:
            return
        if len(line) > 4096:
            raise ValueError("Stream header too long")
        if not line.strip().startswith(b"--"):
            continue
        headers = {}
        for _ in range(20):
            line = response.readline(4097)
            if not line:
                return
            if len(line) > 4096:
                raise ValueError("Stream header too long")
            if not line.strip():
                break
            key, sep, value = line.partition(b":")
            if sep:
                headers[key.strip().lower()] = value.strip()
        else:
            raise ValueError("Too many stream headers")
        length = int(headers.get(b"content-length", b"0"))
        if not 4 <= length <= MAX_FRAME:
            raise ValueError("Invalid JPEG length")
        parts = []
        remaining = length
        while remaining:
            part = response.read(remaining)
            if not part:
                raise ConnectionError("Camera ended a frame early")
            parts.append(part)
            remaining -= len(part)
        frame = b"".join(parts)
        if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
            raise ValueError("Invalid JPEG frame")
        yield frame
