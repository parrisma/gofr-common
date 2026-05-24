# GOFR Base Image
# Shared base image for all GOFR projects (gofr-dig, gofr-plot, gofr-np, gofr-doc)
# Build: docker build -t gofr-base:latest -f docker/base/Dockerfile .
# 
# This image provides:
# - Ubuntu 24.04 base
# - Python 3.12 with venv support
# - UV package manager
# - System libraries for PDF/graphics rendering (WeasyPrint, matplotlib, etc.)
# - Common fonts

FROM ubuntu:24.04

# Remove non-essential users
RUN for user in games man news list irc gnats ubuntu; do \
  if id "$user" >/dev/null 2>&1; then \
  userdel "$user"; \
  fi; \
  done

# Remove non-essential groups
RUN for group in games man news list irc gnats ubuntu; do \
  if getent group "$group" >/dev/null 2>&1; then \
  groupdel "$group"; \
  fi; \
  done

# Install system dependencies
RUN apt-get -o Acquire::Retries=5 update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y -o Acquire::Retries=5 --no-install-recommends \
  wget \
  build-essential \
  ca-certificates \
  libssl-dev \
  libffi-dev \
  zlib1g-dev \
  libbz2-dev \
  libreadline-dev \
  libsqlite3-dev \
  curl \
  jq \
  iputils-ping \
  git \
  sudo \
  libpango-1.0-0 \
  libpango1.0-dev \
  libpangoft2-1.0-0 \
  libcairo2 \
  libcairo2-dev \
  libgdk-pixbuf2.0-0 \
  libgdk-pixbuf2.0-dev \
  && rm -rf /var/lib/apt/lists/*

# Install fonts for matplotlib/PDF rendering
RUN apt-get -o Acquire::Retries=5 update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y -o Acquire::Retries=5 --no-install-recommends \
  fontconfig \
  fonts-dejavu \
  fonts-dejavu-core \
  fonts-dejavu-extra \
  fonts-liberation \
  fonts-liberation2 \
  && fc-cache -f -v \
  && rm -rf /var/lib/apt/lists/*

# Install uv (Python package manager) directly onto PATH.
RUN curl --retry 5 --retry-all-errors -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh \
  && /usr/local/bin/uv --version

# Install Python 3.12 from Ubuntu 24.04 packages.
RUN apt-get -o Acquire::Retries=5 update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y -o Acquire::Retries=5 python3.12 python3.12-venv \
  && rm -rf /var/lib/apt/lists/*

# Verify installations
RUN uv --version && python3.12 --version

# Set Python 3.12 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
  && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# Create standard gofr user (projects can override UID/GID via build args)
ARG USER_NAME=gofr
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid ${USER_GID} ${USER_NAME} \
  && useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USER_NAME} \
  && echo "${USER_NAME} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/${USER_NAME} \
  && chmod 0440 /etc/sudoers.d/${USER_NAME}

# Set up standard directory structure
RUN mkdir -p /home/${USER_NAME}/devroot \
  && chown -R ${USER_NAME}:${USER_NAME} /home/${USER_NAME}

WORKDIR /home/${USER_NAME}/devroot

USER ${USER_NAME}

# Labels for identification
LABEL org.opencontainers.image.source="https://github.com/parrisma/gofr-common"
LABEL org.opencontainers.image.description="GOFR shared base image with Python 3.12, UV, and system dependencies"
LABEL org.opencontainers.image.version="1.0.0"
