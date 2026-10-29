# Renders ChicanoDev VHS episodes on a real Linux filesystem and burns in captions.
# Build: docker build -t chicanodev-vhs videos/docker
FROM ghcr.io/charmbracelet/vhs:v0.12.1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tree htop procps sudo zip unzip iputils-ping curl wget \
      plocate file man-db less \
 && rm -rf /var/lib/apt/lists/*

# Debian trixie has no IBM Plex package; brand font comes from the pinned upstream release.
RUN curl -fsSL -o /tmp/plex-mono.zip \
      "https://github.com/IBM/plex/releases/download/%40ibm%2Fplex-mono%401.1.0/ibm-plex-mono.zip" \
 && mkdir -p /usr/share/fonts/ibm-plex-mono \
 && unzip -j -o /tmp/plex-mono.zip '*.ttf' -d /usr/share/fonts/ibm-plex-mono \
 && rm /tmp/plex-mono.zip \
 && fc-cache -f \
 && fc-list | grep -q "IBM Plex Mono"

# Demo user for the permissions/sudo episodes; tapes run as this user.
RUN useradd -m -s /bin/bash dave \
 && echo 'dave ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/dave

USER dave
WORKDIR /vhs
