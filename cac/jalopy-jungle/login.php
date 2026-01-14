<?php
require_once 'db_connect.php';

$data = json_decode(file_get_contents("php://input"));

if (!isset($data->email) || !isset($data->password)) {
    echo json_encode(["success" => false, "message" => "Missing email or password."]);
    exit;
}


$email = filter_var(trim($data->email), FILTER_SANITIZE_EMAIL);
$password = trim($data->password);

try {
    $stmt = $pdo->prepare("SELECT id, email, password, is_premium, last_login FROM users WHERE email = ?");
    $stmt->execute([$email]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($user && password_verify($password, $user['password'])) {
        // Update last_login to current time
        $updateStmt = $pdo->prepare("UPDATE users SET last_login = NOW() WHERE id = ?");
        $updateStmt->execute([$user['id']]);

        // Password is correct
        echo json_encode([
            "success" => true,
            "user" => [
                "email" => $user['email'],
                "is_premium" => (bool)$user['is_premium'],
                "last_login" => $user['last_login']
            ]
        ]);
    } else {
        echo json_encode(["success" => false, "message" => "Invalid email or password."]);
    }
} catch (PDOException $e) {
    echo json_encode(["success" => false, "message" => "Database error."]);
}
?>