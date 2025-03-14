from werkzeug.security import generate_password_hash

hash = generate_password_hash("admin123")
print(hash)
"pbkdf2:sha256:260000$3LESq315$6f074a3d958ad256ced33cc72dfb79fda306ea53eb4d171d4c1bee4881e778c1"
