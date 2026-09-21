from passlib.context import CryptContext

# Configure the hashing algorithm
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# this function take a plaintext password and return the hashed password
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# used during login to check whether the password the user typed matches the stored hashed password
def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)