# CodeLens

## MongoDB Replica Set (Local)

This repository includes a simple Docker Compose setup to run a 3-node MongoDB replica set locally for development and testing.

Files added:
- `docker-compose.yml` — defines `mongo1`, `mongo2`, `mongo3`, and `mongo-init` services.
- `scripts/init-replica.js` — JS script that initiates the replica set.
- `scripts/wait-and-init.sh` — helper script that waits for MongoDB to be available then runs the init script.

Quick start:

1. Ensure Docker and Docker Compose are installed.
2. Start the cluster:

```
docker compose up -d
```

3. Monitor the init logs (optional):

```
docker compose logs -f mongo-init
```

4. Verify the replica set status:

```
docker exec -it mongo1 mongo --eval "rs.status()"
```

Stop and remove the cluster and volumes:

```
docker compose down -v
```

Notes:
- The init container runs once and attempts to initiate the replica set. Re-running `docker compose up` after an initial setup will keep the replica set as-is.
- Exposed ports: `27017` (mongo1), `27018` (mongo2 -> container 27017), `27019` (mongo3 -> container 27017).
