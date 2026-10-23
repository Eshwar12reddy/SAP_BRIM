from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.schemas.auth import UserRegister, UserLogin, Token, UserResponse, CustomInstructionsUpdate
from backend.app.security.auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_in.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists."
        )

    # First registered user can optionally be an admin
    user_count = db.query(User).count()
    is_first_user = (user_count == 0)
    user_role = "admin" if is_first_user else (user_in.role or "consultant")

    new_user = User(
        email=user_in.email.lower(),
        name=user_in.name.strip(),
        password_hash=hash_password(user_in.password),
        is_admin=is_first_user,
        role=user_role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(data={"sub": new_user.id, "email": new_user.email, "role": new_user.role})
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(new_user)
    )

@router.post("/login", response_model=Token)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email.lower()).first()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )

@router.post("/demo", response_model=Token)
def demo_login(db: Session = Depends(get_db)):
    demo_email = "consultant@clyptus.ai"
    user = db.query(User).filter((User.email == demo_email) | (User.email == "consultant@clyptusap.ai")).first()
    if not user:
        user = User(
            email=demo_email,
            name="SAP Consultant",
            password_hash=hash_password("clyptusDemo2026!"),
            is_admin=False,
            role="consultant",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)

@router.get("/custom-instructions", response_model=CustomInstructionsUpdate)
def get_custom_instructions(current_user: User = Depends(get_current_user)):
    return CustomInstructionsUpdate(
        about_user=current_user.custom_instructions_about_user,
        how_to_respond=current_user.custom_instructions_how_to_respond,
    )

@router.put("/custom-instructions", response_model=CustomInstructionsUpdate)
def update_custom_instructions(
    data: CustomInstructionsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.about_user is not None:
        user.custom_instructions_about_user = data.about_user.strip() or None
    if data.how_to_respond is not None:
        user.custom_instructions_how_to_respond = data.how_to_respond.strip() or None
    db.commit()
    db.refresh(user)
    return CustomInstructionsUpdate(
        about_user=user.custom_instructions_about_user,
        how_to_respond=user.custom_instructions_how_to_respond,
    )
