# Add Neo4J's official apt repository
RUN apt-get install -y wget gnupg \
    && wget -O- https://debian.neo4j.com/neotechnology.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/neotechnology.gpg \
    && echo 'deb [signed-by=/etc/apt/keyrings/neotechnology.gpg] https://debian.neo4j.com stable latest' \
        > /etc/apt/sources.list.d/neo4j.list \
    && apt-get update \
    && apt-get install -y neo4j \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Redirect all Neo4J data directories to the project user's home so they land
# on named volumes and remain writable under a read_only root filesystem.
# We delete any existing occurrence of each key (commented or not) then append
# the authoritative value — this is robust against format variations in the
# default neo4j.conf (e.g. "# key=val" vs "#key=val" vs a different default).
RUN sed -i \
        -e '/server\.directories\.data/d' \
        -e '/server\.directories\.logs/d' \
        -e '/server\.directories\.plugins/d' \
        -e '/server\.directories\.import/d' \
        -e '/server\.directories\.run/d' \
        -e '/server\.bolt\.listen_address/d' \
        -e '/server\.http\.listen_address/d' \
        /etc/neo4j/neo4j.conf \
    && printf '%s\n' \
        "server.directories.data=/home/${USER}/.neo4j/data" \
        "server.directories.logs=/home/${USER}/.neo4j/logs" \
        "server.directories.plugins=/home/${USER}/.neo4j/plugins" \
        "server.directories.import=/home/${USER}/.neo4j/import" \
        "server.directories.run=/home/${USER}/.neo4j/run" \
        "server.bolt.listen_address=0.0.0.0:7687" \
        "server.http.listen_address=0.0.0.0:7474" \
        >> /etc/neo4j/neo4j.conf

# Transfer ownership of all neo4j-managed paths to the project user so the
# container can start under user: ${CONTAINER_USER_ID} (no root at runtime).
RUN chown -R ${USER}:${USER} \
        /etc/neo4j \
        /var/lib/neo4j \
        /var/log/neo4j \
        /usr/share/neo4j
