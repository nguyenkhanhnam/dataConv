##################
### Build CKAN ###
##################
FROM ubuntu:18.04 as ckanbuild

# Set CKAN version to build
ENV GIT_URL=https://github.com/ckan/ckan.git
ENV GIT_BRANCH=ckan-2.9.1

# Set src dirs
ENV SRC_DIR=/srv/app/src
ENV PIP_SRC=${SRC_DIR}

WORKDIR ${SRC_DIR}

RUN apt-get update

# Packages to build CKAN requirements and plugins
RUN apt-get -y install \
        git \
        curl \
        python3 \
        libpq-dev \
        linux-headers-$(uname -r) \
        gcc \
        make \
        g++ \
        autoconf \
        automake \
        libtool \
        patch \
        musl-dev \
        libpcre3-dev \
        libpcre3 \
        python3-dev \
        libffi-dev \
        libxml2-dev \
        libxslt-dev

# Link python to python3
RUN ln -s /usr/bin/python3 /usr/bin/python

# Create the src directory
RUN mkdir -p ${SRC_DIR}

# Install pip
RUN curl -o ${SRC_DIR}/get-pip.py https://bootstrap.pypa.io/get-pip.py && \
    python ${SRC_DIR}/get-pip.py

# Downgrade setuptools so that CKAN requirements can be built
RUN pip install setuptools==44.1.0

# Fetch and build CKAN and requirements
RUN pip install -e git+${GIT_URL}@${GIT_BRANCH}#egg=ckan
# Copy patches and apply patches script
COPY ./patches ${SRC_DIR}/patches
COPY ./scripts/apply_ckan_patches.sh ${SRC_DIR}/apply_ckan_patches.sh
# Apply patches
RUN ${SRC_DIR}/apply_ckan_patches.sh
RUN rm -rf /srv/app/src/ckan/.git
RUN pip wheel --wheel-dir=/wheels -r ckan/requirements.txt
RUN pip wheel --wheel-dir=/wheels uwsgi==2.0.19.1 gevent==20.6.2 greenlet==0.4.16


###########################
### Default-Extensions ####
###########################
FROM ubuntu:18.04 as extbuild

# Set src dirs
ENV SRC_DIR=/srv/app/src
ENV PIP_SRC=${SRC_DIR}

# List of default extensions
ENV DEFAULT_EXTENSIONS envvars

# Locations and tags, please use specific tags or revisions
ENV ENVVARS_GIT_URL=https://github.com/okfn/ckanext-envvars
ENV ENVVARS_GIT_BRANCH=0.0.1

RUN apt-get update

RUN apt-get -y install \
        git \
        curl \
        python3 \
        python3-dev

# Link python to python3
RUN ln -s /usr/bin/python3 /usr/bin/python

# Create the src directory
RUN mkdir -p ${SRC_DIR}

# Install pip
RUN curl -o ${SRC_DIR}/get-pip.py https://bootstrap.pypa.io/get-pip.py && \
    python ${SRC_DIR}/get-pip.py

# Fetch and build the default CKAN extensions
RUN pip wheel --wheel-dir=/wheels git+${ENVVARS_GIT_URL}@${ENVVARS_GIT_BRANCH}#egg=ckanext-envvars

############
### MAIN ###
############
FROM ubuntu:18.04

MAINTAINER Keitaro Inc <info@keitaro.com>

ENV APP_DIR=/srv/app
ENV SRC_DIR=/srv/app/src
ENV DATA_DIR=/srv/app/data
ENV PIP_SRC=${SRC_DIR}
ENV CKAN_SITE_URL=http://localhost:5000
ENV CKAN__PLUGINS envvars image_view text_view recline_view datastore datapusher mysql2mongodb

WORKDIR ${APP_DIR}

RUN apt-get update

# Install necessary packages to run CKAN

RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata

RUN apt-get -y install git \
        bash \
        gettext \
        curl \
        postgresql-client \
        python3 \
        # libmagic \
        libmagic-dev \
        libpcre3-dev \
        libpcre3 \
        # libxslt \
        libxslt1-dev \
        libxml2 \
        locales \
        python3-distutils \
        python3-apt \
        libpython3.6-dev \
        apache2-utils && \
    # Create SRC_DIR
    mkdir -p ${SRC_DIR} && \
    # Link python to python3
    ln -s /usr/bin/python3 /usr/bin/python

# Install pip
RUN curl -o ${SRC_DIR}/get-pip.py https://bootstrap.pypa.io/get-pip.py && \
    python ${SRC_DIR}/get-pip.py

# Get artifacts from build stages
COPY --from=ckanbuild /wheels /srv/app/wheels
COPY --from=extbuild /wheels /srv/app/ext_wheels
COPY --from=ckanbuild /srv/app/src/ckan /srv/app/src/ckan

# Additional install steps for build stages artifacts
RUN pip install --no-index --find-links=/srv/app/wheels uwsgi gevent

# Create a local user and group to run the app
RUN addgroup --system --gid 92 ckan && \
    # adduser -u 92 -h /srv/app -H -D -S -G ckan ckan
    adduser --home /srv/app --uid 92 --ingroup ckan --system --disabled-password ckan && \
    usermod -aG sudo ckan

ARG CACHEBUST=1
RUN pip install -e git+https://github.com/ligthsworn/ckanext-mysql2mongodb#egg=ckanext-mysql2mongodb --no-cache-dir

RUN locale-gen en_US.UTF-8

ENV LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8


# Install CKAN
RUN pip install -e /srv/app/src/ckan && \
    cd ${SRC_DIR}/ckan && \
    cp who.ini ${APP_DIR} && \
    pip install --no-index --find-links=/srv/app/wheels -r requirements.txt && \
    # Install default CKAN extensions
    pip install --no-index --find-links=/srv/app/ext_wheels ckanext-envvars && \
    # Create and update CKAN config
    # Set timezone
    echo "UTC" >  /etc/timezone && \
    # Generate CKAN config
        ckan generate config ${APP_DIR}/production.ini && \
        # Configure plugins
        ckan config-tool ${APP_DIR}/production.ini "ckan.plugins = ${CKAN__PLUGINS}" && \
        # Create the data directory
        mkdir ${DATA_DIR} && \
        # Webassets can't be loaded from env variables at runtime, it needs to be in the config so that it is created
        ckan config-tool ${APP_DIR}/production.ini "ckan.webassets.path = ${DATA_DIR}/webassets" && \
        # Set the default level for extensions to INFO
        ckan config-tool ${APP_DIR}/production.ini -s logger_ckanext -e level=INFO && \
        # Change ownership to app user
        chown -R ckan:ckan /srv/app


# Remove wheels
RUN rm -rf /srv/app/wheels /srv/app/ext_wheels

# Copy necessary scripts
COPY setup/app ${APP_DIR}

# Create entrypoint directory for children image scripts
ONBUILD RUN mkdir docker-entrypoint.d

# Create afterinit directory for children image scripts
ONBUILD RUN mkdir docker-afterinit.d

RUN mkdir ${APP_DIR}/ext_requirements
COPY ext_setup/requirements.txt ${APP_DIR}/ext_requirements/
RUN pip install -r ${APP_DIR}/ext_requirements/requirements.txt

RUN apt-get update

RUN apt-get -y install mysql-client
# RUN apt-get -y install mongodb-tools
RUN apt-get -y install openjdk-11-jdk
RUN apt-get -y install zip

EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 CMD curl --fail http://localhost:5000/api/3/action/status_show || exit 1

USER ckan

CMD ["/srv/app/start_ckan.sh"]
