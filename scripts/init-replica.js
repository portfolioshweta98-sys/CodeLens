// init-replica.js
// Initiate a replica set named rs0 with three members.

try {
  rs.initiate({
    _id: "rs0",
    members: [
      { _id: 0, host: "mongo1:27017" },
      { _id: 1, host: "mongo2:27017" },
      { _id: 2, host: "mongo3:27017" }
    ]
  });
  print("rs.initiate() called");
} catch (e) {
  print('init error: ' + e);
}
