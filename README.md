The following files should be reviewed and updated according to the project's needs.

### .env
Defines environment variables common across all containers. This file contains default values that most certainly need to be modified.

### docker-compose.yaml
Defines services and build-time configuration arguments. The `<< *base` directive should be used in the definition of new services to reduce the possibility of attacks from within the containers.

### git.dockerfile
Defines a container for source repository related operations. The primary focus of this seed is security. To prevent an adversary from obtaining the repository keys by injecting malware trough a dependency or script, all Git commands are run in a separate container. This configuration should only be modified only to fit the specific project layout. To mitigate potential security risks, nothing that deviates from the container's intended purpose should be added.

### dev.dockerfile
Defines a container for developmental purposes. This configuration should be adjusted to establish a development environment suitable for the projects at hand. Ideally, any commands added into this configuration should be executed by a non-root user, i.e. following the `USER=${USER}` line. This precaution is particularly important for commands that might execute untrusted code, such as `npm install`. For additional level of protection a separate container might be created for every repository in the project.
