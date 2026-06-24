FROM python:3.10-slim-bookworm

# ---------------------------------------------------------------------------
# System dependencies
#   openjdk-17-jre-headless  — Audiveris runtime
#   poppler-utils            — pdf2image (pdftoppm)
#   fluidsynth               — MIDI → WAV synthesis
#   fluid-soundfont-gm       — FluidR3_GM.sf2 choral-capable GM soundfont
#   ffmpeg                   — WAV → MP3 encoding
#   libgl1 + libglib2.0-0    — OpenCV headless runtime
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless \
        poppler-utils \
        fluidsynth \
        fluid-soundfont-gm \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        wget \
        unzip \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# ---------------------------------------------------------------------------
# Audiveris self-hosted OMR engine
# As of 5.10.x, releases ship OS-specific installers instead of a generic zip.
# We install the Ubuntu .deb (jpackage bundle, self-contained runtime).
# Override AUDIVERIS_VERSION or AUDIVERIS_URL at build time if needed.
# ---------------------------------------------------------------------------
ARG AUDIVERIS_VERSION=5.10.2
ARG AUDIVERIS_DEB=Audiveris-${AUDIVERIS_VERSION}-ubuntu24.04-x86_64.deb
ARG AUDIVERIS_URL=https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/${AUDIVERIS_DEB}

RUN wget -q "${AUDIVERIS_URL}" -O /tmp/audiveris.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/audiveris.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/audiveris.deb \
    && BIN="$(find /opt -type f -path '*/bin/Audiveris' | head -n1)" \
    && test -n "${BIN}" \
    && mkdir -p /opt/audiveris/bin \
    && { [ "${BIN}" = /opt/audiveris/bin/Audiveris ] || ln -sf "${BIN}" /opt/audiveris/bin/Audiveris; }

# ---------------------------------------------------------------------------
# Python application
# ---------------------------------------------------------------------------
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# ---------------------------------------------------------------------------
# Runtime defaults (overridden by env_file in docker-compose)
# ---------------------------------------------------------------------------
ENV DATA_DIR=/data \
    PUBLIC_BASE_URL=http://localhost \
    AUDIVERIS_CMD=/opt/audiveris/bin/Audiveris \
    SOUNDFONT_PATH=/usr/share/sounds/sf2/FluidR3_GM.sf2 \
    FLUIDSYNTH_CMD=fluidsynth \
    FFMPEG_CMD=ffmpeg \
    OMR_CONFIDENCE_THRESHOLD=0.5 \
    OMR_MANUAL_THRESHOLD=0.4 \
    STORAGE_BACKEND=local \
    USE_CELERY=true \
    CELERY_BROKER_URL=redis://redis:6379/0 \
    CELERY_RESULT_BACKEND=redis://redis:6379/1

VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
