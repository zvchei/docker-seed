# DockerSeed

DockerSeed is a lightweight, Docker-based environment designed for secure development tool management in isolated containers.

## Project Structure

- `.env` – Environment variables for container configuration.
- `credentials/` – Directory for SSH keys used with Git.
- `docker-compose.yml` – Docker Compose configuration file where services are defined. Add or remove services as needed.
- `services/` – Contains directories for each service, including Dockerfiles and configuration files.
- `services/common/` – Shared files used across services. New services should extend `common/base.yaml` to inherit security and configuration settings.

### Available Services

- `code` – A containerized VS Code server accessible via a web browser.
- `git` – A container for Git operations with pre-configured aliases.
- `cli` – A lightweight container for building and running the project in a terminal environment.
- `gui` – A container for running the project as a GUI application through VNC.

## Prerequisites

- Docker
- Docker Compose

## Setup

1. Clone the repository.
2. Create or copy SSH keys into the `credentials/` directory:
   - Follow the instructions in `credentials/README`.
3. Configure environment variables in the `.env` file as needed.
4. Modify `docker-compose.yml` to include or exclude services.
5. Build the containers:
   ```bash
   docker-compose build
   ```

## Usage

### Start the Development Environment

```bash
docker-compose up -d code
```

Open a browser and navigate to `http://localhost:8080`.

Example:

```bash
some-browser --kiosk http://localhost:8080
```

The `code` container includes Git but does not mount SSH keys to mitigate the risk of malicious extensions or packages accessing them.

### Use the Git Container for Repository Access

```bash
docker-compose run git
```

- SSH keys are stored in the `credentials/` directory. Ensure this directory is secure and excluded from version control (see `.gitignore`).
- SSH keys are mounted only into the `git` container for use with Git and SSH.

### Run the Project as a Terminal Application

The `cli` container does not include development tools by default. Modify its Dockerfile to install the necessary tools according to project requirements.

This container can be used to install dependencies and build the project if doing so in the `code` container is considered insecure.

```bash
docker-compose run cli bash
```

For high-security environments, the `cli` container should serve as a base for creating a dedicated build container to separate building and execution environments.

To run the `cli` container:

```bash
docker-compose run cli
```

If ports need to be exposed to the host:

```bash
docker-compose up cli
# or
docker-compose run --service-ports cli
```

### Run the Project as a GUI Application

```bash
docker-compose up gui
```

Connect to `localhost:8900` using a VNC client.

### Create a New Service

1. Create a new directory inside `services/`.
2. Add a `Dockerfile` to the new directory. Refer to other services for examples.
3. Create a `<service>.yaml` file to configure the service, preferably extending `common/base.yaml`. Two base configurations are provided: `base` for common settings and `gpu` for enabling access to the GPU of the host. See other services for reference.
4. Add the new service to `docker-compose.yml`.
5. Build the container:
   ```bash
   docker-compose build <service>
   ```

## License

This project is licensed under the MIT No Attribution License.
See the `LICENSE` file for details.
