<?php
// Prevent PHP errors from being output directly to the browser (breaks JSON)
ini_set('display_errors', 0);
error_reporting(E_ALL);

// Database configuration - UPDATE THESE WITH YOUR GODADDY DETAILS
$host = 'localhost';      // Usually 'localhost' on GoDaddy shared hosting
$dbname = 'cac_profit'; // Your database name
$username = 'cac_appuser'; // Your database username
$password = 'cac_appuser'; // Your database password

// CORS Headers
// If your frontend is on a different domain (e.g. GitHub Pages), change * to that domain
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: POST, GET, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type");
header('Content-Type: application/json');

// Handle preflight requests
if ($_SERVER['REQUEST_METHOD'] == 'OPTIONS') {
    exit(0);
}

try {
    $pdo = new PDO("mysql:host=$host;dbname=$dbname;charset=utf8", $username, $password);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(["success" => false, "message" => "Database connection failed: " . $e->getMessage()]);
    exit;
}
?>