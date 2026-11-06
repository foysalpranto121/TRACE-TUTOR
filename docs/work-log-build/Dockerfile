FROM trace-tutor-runner:1
USER 0:0
RUN apt-get update && apt-get install --no-install-recommends -y \
    python3-docx python3-pip python3-pil libreoffice-writer poppler-utils \
    fonts-crosextra-carlito fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install --break-system-packages pdf2image
WORKDIR /work
