"""Shared pytest fixtures for the maintenance assistant."""

from datetime import UTC, date, datetime
from itertools import count
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    DashboardPermission,
    Department,
    Employee,
    ErrorEntry,
    GeneratedDocument,
    InventoryMaterial,
    Machine,
    Priority,
    Role,
    Task,
    TaskStatus,
    User,
)
from app.permissions import upsert_default_permissions

_USER_COUNTER = count(1)


@pytest.fixture()
def app(tmp_path):
    """Create an isolated Flask app with an in-memory test database."""

    class TestingConfig:
        """Provide deterministic test settings without reading production data."""

        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        JWT_SECRET_KEY = "test-secret-key-with-enough-length"
        AI_PROVIDER = "mock"
        EMBEDDING_PROVIDER = "hashing"
        # The legacy suites exercise the rule-based router directly; agent tests
        # opt in with AI_CHAT_MODE="agent". Checkpoints stay in-process.
        AI_CHAT_MODE = "legacy"
        AI_AGENT_CHECKPOINTER = "memory"
        OPENAI_API_KEY = ""
        OPENAI_MODEL = "test-model"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        DOCUMENTS_FOLDER = str(tmp_path / "documents")
        MANUALS_FOLDER = str(tmp_path / "manuals")
        KNOWLEDGE_FOLDER = str(tmp_path / "knowledge")
        BACKUP_FOLDER = str(tmp_path / "backups")
        LOG_DIR = str(tmp_path / "logs")
        MAIL_DRY_RUN = True
        MAIL_ENABLED = False
        MAIL_FROM = "noreply@example.test"

    application = create_app(TestingConfig)

    with application.app_context():
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    """Return a Flask test client for the isolated app."""
    return app.test_client()


@pytest.fixture()
def make_user(app):
    """Return a factory that creates users with default dashboard permissions."""

    def _make_user(
        username=None,
        role=Role.PRODUKTION,
        department_name="Produktion",
        password="password",
        is_active=True,
    ):
        """Create one test user and return its identity data."""
        role_value = role if isinstance(role, Role) else Role(role)
        suffix = next(_USER_COUNTER)
        username_value = username or f"user_{suffix}"
        email_value = f"{username_value}@example.test"

        with app.app_context():
            department = None
            if department_name:
                department = Department.query.filter_by(name=department_name).first()
                if not department:
                    department = Department(name=department_name)
                    db.session.add(department)
                    db.session.flush()

            user = User(
                username=username_value,
                email=email_value,
                role=role_value,
                department=department,
                is_active=is_active,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            upsert_default_permissions(user)
            db.session.commit()
            return {
                "id": user.id,
                "username": username_value,
                "email": email_value,
                "password": password,
                "role": role_value.value,
                "department": department.name if department else None,
            }

    return _make_user


@pytest.fixture()
def auth_headers(client):
    """Return a helper that logs in and builds JWT authorization headers."""

    def _auth_headers(login, password="password"):
        """Authenticate a user and return a bearer token header."""
        response = client.post(
            "/api/v1/auth/login",
            json={"login": login, "password": password},
        )
        assert response.status_code == 200, response.get_json()
        token = response.get_json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _auth_headers


@pytest.fixture()
def set_dashboard_permission(app):
    """Return a helper that updates one dashboard permission for a user."""

    def _set_dashboard_permission(
        username,
        dashboard,
        can_view=True,
        can_write=False,
        employee_access_level="none",
    ):
        """Create or update one dashboard permission for a username."""
        with app.app_context():
            user = User.query.filter_by(username=username).one()
            permission = DashboardPermission.query.filter_by(
                user_id=user.id,
                dashboard=dashboard,
            ).first()
            if not permission:
                permission = DashboardPermission(user=user, dashboard=dashboard)
                db.session.add(permission)
            permission.can_view = can_view
            permission.can_write = can_write
            permission.employee_access_level = (
                employee_access_level if dashboard == "employees" else "none"
            )
            db.session.commit()

    return _set_dashboard_permission


@pytest.fixture()
def make_task(app):
    """Return a factory that creates tasks directly in the test database."""

    def _make_task(
        title,
        creator_username,
        department_name="Produktion",
        priority=Priority.NORMAL,
        status=TaskStatus.OPEN,
        due_date_value=None,
        description="Test task",
    ):
        """Create a task and return its database id."""
        with app.app_context():
            user = User.query.filter_by(username=creator_username).one()
            department = Department.query.filter_by(name=department_name).one()
            task = Task(
                title=title,
                description=description,
                priority=priority,
                status=status,
                due_date=due_date_value or date.today(),
                department=department,
                created_by=user.id,
            )
            db.session.add(task)
            db.session.commit()
            return task.id

    return _make_task


@pytest.fixture()
def make_error_entry(app):
    """Return a factory that creates error catalog entries."""

    def _make_error_entry(
        machine,
        error_code,
        title,
        department_name="Produktion",
        description="Test description",
        possible_causes="Test cause",
        solution="Test solution",
    ):
        """Create an error entry and return its database id."""
        with app.app_context():
            department = Department.query.filter_by(name=department_name).one()
            entry = ErrorEntry(
                machine=machine,
                error_code=error_code,
                title=title,
                description=description,
                possible_causes=possible_causes,
                solution=solution,
                department=department,
            )
            db.session.add(entry)
            db.session.commit()
            return entry.id

    return _make_error_entry


@pytest.fixture()
def make_employee(app):
    """Return a factory that creates employees directly."""

    def _make_employee(
        personnel_number="P-100",
        name="Max Mustermann",
        department="Produktion",
        team=1,
        salary_group="E3",
        qualifications="CNC",
        favorite_machine="Anlage 1",
    ):
        """Create an employee and return its database id."""
        with app.app_context():
            employee = Employee(
                personnel_number=personnel_number,
                name=name,
                birth_date=date(1990, 1, 1),
                city="Berlin",
                street="Teststrasse 1",
                postal_code="10115",
                department=department,
                shift_model="2-Schicht",
                current_shift="Frueh",
                team=team,
                salary_group=salary_group,
                qualifications=qualifications,
                favorite_machine=favorite_machine,
            )
            db.session.add(employee)
            db.session.commit()
            return employee.id

    return _make_employee


@pytest.fixture()
def make_machine(app):
    """Return a factory that creates machines directly."""

    def _make_machine(
        name="Anlage 1",
        produced_item="Gehaeuse",
        required_employees=1,
    ):
        """Create a machine and return its database id."""
        with app.app_context():
            machine = Machine(
                name=name,
                produced_item=produced_item,
                required_employees=required_employees,
            )
            db.session.add(machine)
            db.session.commit()
            return machine.id

    return _make_machine


@pytest.fixture()
def make_material(app):
    """Return a factory that creates inventory materials directly."""

    def _make_material(name, unit_cost, quantity, machine_id=None):
        """Create an inventory material and return its database id."""
        with app.app_context():
            material = InventoryMaterial(
                name=name,
                unit_cost=unit_cost,
                quantity=quantity,
                machine_id=machine_id,
            )
            db.session.add(material)
            db.session.commit()
            return material.id

    return _make_material


@pytest.fixture()
def make_document(app):
    """Return a factory that creates generated document metadata and files."""

    def _make_document(
        task_id,
        created_by,
        relative_path="2026/05/task_1/maintenance_report.html",
        department="Produktion",
        machine="Anlage 1",
    ):
        """Create a generated document record and matching file."""
        with app.app_context():
            document_path = Path(app.config["DOCUMENTS_FOLDER"]) / relative_path
            document_path.parent.mkdir(parents=True, exist_ok=True)
            document_path.write_text("<html>report</html>", encoding="utf-8")
            document = GeneratedDocument(
                task_id=task_id,
                document_type="maintenance_report",
                title="Wartungsbericht",
                relative_path=relative_path,
                department=department,
                machine=machine,
                created_by=created_by,
                created_at=datetime.now(UTC),
            )
            db.session.add(document)
            db.session.commit()
            return document.id

    return _make_document


def create_generated_document(app, task_id, created_by, relative_path, department):
    """Create generated document metadata for tests that need custom paths."""
    with app.app_context():
        document = GeneratedDocument(
            task_id=task_id,
            document_type="maintenance_report",
            title="Wartungsbericht",
            relative_path=relative_path,
            department=department,
            machine="Anlage 1",
            created_by=created_by,
            created_at=datetime.now(UTC),
        )
        db.session.add(document)
        db.session.commit()
        return document.id
