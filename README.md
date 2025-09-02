# DockerSeed

DockerSeed is a lightweight, Docker-based environment designed for secure development in isolated containers.

## Quick Start

**1.** Clone the repository.

**2.** Run the setup script:
   ```bash
   ./setup.sh
   ```
**3.** Run VS Code:
   ```bash
   docker-compose up code
   
   # Navigate to http://localhost:8080. Kiosk mode is recommended:
   google-chrome --new --kiosk http://localhost:8080
   ```
**4.** Start services:
   ```bash
   docker-compose up <service_name>
   ```

## License

This project is licensed under the MIT No Attribution License.
See the `LICENSE` file for details.
