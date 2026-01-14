<?php
require_once 'db_connect.php';

// Get JSON input
$data = json_decode(file_get_contents("php://input"));

if (!isset($data->email) || !isset($data->password)) {
    echo json_encode(["success" => false, "message" => "Missing email or password."]);
    exit;
}

$email = filter_var(trim($data->email), FILTER_SANITIZE_EMAIL);
$password = trim($data->password);

if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    echo json_encode(["success" => false, "message" => "Invalid email format."]);
    exit;
}

// Check if email already exists
$stmt = $pdo->prepare("SELECT id FROM users WHERE email = ?");
$stmt->execute([$email]);
if ($stmt->rowCount() > 0) {
    echo json_encode(["success" => false, "message" => "Email already registered."]);
    exit;
}

// Hash password
$hashed_password = password_hash($password, PASSWORD_DEFAULT);

// Insert user
try {
    // Default is_premium to 0
    $stmt = $pdo->prepare("INSERT INTO users (email, password, is_premium) VALUES (?, ?, 0)");
    if ($stmt->execute([$email, $hashed_password])) {
        echo json_encode([
            "success" => true,
            "user" => ["email" => $email, "is_premium" => 0]
        ]);
    } else {
        echo json_encode(["success" => false, "message" => "Registration failed."]);
    }
} catch (PDOException $e) {
    echo json_encode(["success" => false, "message" => "Database error: " . $e->getMessage()]);
}
?>