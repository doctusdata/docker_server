const config = require('./app.json');

module.exports = {
    host: config.database.host,
    user: config.database.user,
    password: config.database.password,
    database: config.database.database,
    port: config.database.port,
    // Added for case sensitivity in PostgreSQL
    options: '-c search_path=public'
};