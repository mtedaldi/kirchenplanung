"""
SQLAlchemy-Modelle — direkte Abbildung des Datenbankschemas V1.3.
Konventionen:
  - UUID als Primärschlüssel (server_default für PostgreSQL)
  - TIMESTAMPTZ via DateTime(timezone=True)
  - Soft Delete via deleted_at
  - Enums als Python-Enum + PostgreSQL-ENUM
"""
import enum
import uuid
from datetime import datetime, time, date

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey,
    Integer, String, Text, Time, UniqueConstraint, event,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


# =============================================================================
# ENUMS
# =============================================================================

class EventStatus(str, enum.Enum):
    requested = "requested"
    approved = "approved"
    confirmed = "confirmed"
    rejected = "rejected"
    cancelled = "cancelled"


class LocationType(str, enum.Enum):
    building = "building"
    room = "room"
    outdoor = "outdoor"
    other = "other"


class DependencyType(str, enum.Enum):
    exclusive = "exclusive"
    shared = "shared"


class AuditAction(str, enum.Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    ANONYMIZE = "ANONYMIZE"


# =============================================================================
# HELPER: UUID-Primärschlüssel
# =============================================================================

def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )


def now_tz() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# =============================================================================
# 1. PERSON
# =============================================================================

class Person(Base):
    __tablename__ = "person"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = now_tz()
    updated_at: Mapped[datetime] = now_tz()

    # Relationships
    app_user: Mapped["AppUser | None"] = relationship(back_populates="person", uselist=False)
    duty_entries: Mapped[list["DutySchedule"]] = relationship(back_populates="person")
    participations: Mapped[list["OccurrenceParticipant"]] = relationship(back_populates="person")


# =============================================================================
# 2. APP_USER
# =============================================================================

class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = uuid_pk()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id"), nullable=False, unique=True
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # nullable: OAuth/Passkey-Erweiterung vorbereitet (Schema V1.3)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = now_tz()

    __table_args__ = (
        # Mindestens eine Auth-Methode (erweiterbar für OAuth/Passkey)
        CheckConstraint("password_hash IS NOT NULL", name="at_least_one_auth_method"),
    )

    # Relationships
    person: Mapped["Person"] = relationship(back_populates="app_user")
    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    created_events: Mapped[list["Event"]] = relationship(
        back_populates="creator", foreign_keys="Event.created_by"
    )
    approved_events: Mapped[list["Event"]] = relationship(
        back_populates="approver", foreign_keys="Event.approved_by"
    )

    @property
    def role_names(self) -> list[str]:
        return [ur.role.name for ur in self.roles if ur.role]


# =============================================================================
# 3. ROLE
# =============================================================================

class Role(Base):
    __tablename__ = "role"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="role")


# =============================================================================
# 4. USER_ROLE
# =============================================================================

class UserRole(Base):
    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True
    )
    granted_at: Mapped[datetime] = now_tz()

    # Relationships
    user: Mapped["AppUser"] = relationship(back_populates="roles", foreign_keys=[user_id])
    role: Mapped["Role"] = relationship(back_populates="user_roles")


# =============================================================================
# 5. LOCATION
# =============================================================================

class Location(Base):
    __tablename__ = "location"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[LocationType] = mapped_column(
        Enum(LocationType, name="location_type"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("location.id"), nullable=True
    )
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = now_tz()

    # Relationships
    children: Mapped[list["Location"]] = relationship(back_populates="parent")
    parent: Mapped["Location | None"] = relationship(back_populates="children", remote_side="Location.id")
    occurrence_locations: Mapped[list["OccurrenceLocation"]] = relationship(back_populates="location")


# =============================================================================
# 6. LOCATION_DEPENDENCY
# =============================================================================

class LocationDependency(Base):
    __tablename__ = "location_dependency"

    id: Mapped[uuid.UUID] = uuid_pk()
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("location.id"), nullable=False
    )
    depends_on_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("location.id"), nullable=False
    )
    type: Mapped[DependencyType] = mapped_column(
        Enum(DependencyType, name="dependency_type"), nullable=False
    )

    __table_args__ = (
        CheckConstraint("location_id <> depends_on_location_id", name="no_self_dependency"),
    )


# =============================================================================
# 7. RESOURCE
# =============================================================================

class Resource(Base):
    __tablename__ = "resource"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = now_tz()

    __table_args__ = (
        CheckConstraint("total_quantity > 0", name="positive_quantity"),
    )


# =============================================================================
# 8. BLACKOUT
# =============================================================================

class Blackout(Base):
    __tablename__ = "blackout"

    id: Mapped[uuid.UUID] = uuid_pk()
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    created_at: Mapped[datetime] = now_tz()

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="blackout_valid_range"),
    )

    # Relationships
    locations: Mapped[list["BlackoutLocation"]] = relationship(
        back_populates="blackout", cascade="all, delete-orphan"
    )


# =============================================================================
# 9. BLACKOUT_LOCATION
# =============================================================================

class BlackoutLocation(Base):
    __tablename__ = "blackout_location"

    blackout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blackout.id", ondelete="CASCADE"), primary_key=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("location.id"), primary_key=True
    )

    # Relationships
    blackout: Mapped["Blackout"] = relationship(back_populates="locations")
    location: Mapped["Location"] = relationship()


# =============================================================================
# 10. EVENT
# =============================================================================

class Event(Base):
    __tablename__ = "event"

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status"),
        nullable=False,
        default=EventStatus.requested,
    )
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Workflow
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Soft Delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = now_tz()
    updated_at: Mapped[datetime] = now_tz()

    __table_args__ = (
        # Self-Approval-Sperre auf DB-Ebene
        CheckConstraint(
            "approved_by IS NULL OR approved_by != created_by",
            name="no_self_approval"
        ),
    )

    # Relationships
    creator: Mapped["AppUser"] = relationship(back_populates="created_events", foreign_keys=[created_by])
    approver: Mapped["AppUser | None"] = relationship(back_populates="approved_events", foreign_keys=[approved_by])
    occurrences: Mapped[list["EventOccurrence"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


# =============================================================================
# 11. EVENT_OCCURRENCE
# =============================================================================

class EventOccurrence(Base):
    __tablename__ = "event_occurrence"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id", ondelete="CASCADE"), nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    has_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_tentative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_occurrence.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = now_tz()

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="occurrence_valid_range"),
    )

    # Relationships
    event: Mapped["Event"] = relationship(back_populates="occurrences")
    locations: Mapped[list["OccurrenceLocation"]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )
    resources: Mapped[list["OccurrenceResource"]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )
    participants: Mapped[list["OccurrenceParticipant"]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )
    blackout_overrides: Mapped[list["BlackoutOverride"]] = relationship(
        back_populates="occurrence"
    )


# =============================================================================
# 12. OCCURRENCE_LOCATION
# =============================================================================

class OccurrenceLocation(Base):
    __tablename__ = "occurrence_location"

    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_occurrence.id", ondelete="CASCADE"), primary_key=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("location.id"), primary_key=True
    )

    # Relationships
    occurrence: Mapped["EventOccurrence"] = relationship(back_populates="locations")
    location: Mapped["Location"] = relationship(back_populates="occurrence_locations")


# =============================================================================
# 13. OCCURRENCE_RESOURCE
# =============================================================================

class OccurrenceResource(Base):
    __tablename__ = "occurrence_resource"

    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_occurrence.id", ondelete="CASCADE"), primary_key=True
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resource.id"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_resource_quantity"),
    )

    # Relationships
    occurrence: Mapped["EventOccurrence"] = relationship(back_populates="resources")
    resource: Mapped["Resource"] = relationship()


# =============================================================================
# 14. OCCURRENCE_PARTICIPANT
# =============================================================================

class OccurrenceParticipant(Base):
    __tablename__ = "occurrence_participant"

    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_occurrence.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id"), primary_key=True
    )
    role: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Snapshots zum Zeitpunkt der Buchung
    name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    email_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    occurrence: Mapped["EventOccurrence"] = relationship(back_populates="participants")
    person: Mapped["Person"] = relationship(back_populates="participations")


# =============================================================================
# 15. BLACKOUT_OVERRIDE
# =============================================================================

class BlackoutOverride(Base):
    __tablename__ = "blackout_override"

    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_occurrence.id"), primary_key=True
    )
    blackout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blackout.id"), primary_key=True
    )
    approved_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime] = now_tz()

    # Relationships
    occurrence: Mapped["EventOccurrence"] = relationship(back_populates="blackout_overrides")


# =============================================================================
# 16. CHANGE_LOG (Audit Log)
# =============================================================================

class ChangeLog(Base):
    __tablename__ = "change_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action"), nullable=False
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True
    )
    changed_at: Mapped[datetime] = now_tz()
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


# =============================================================================
# 17. DUTY_SCHEDULE
# =============================================================================

class DutySchedule(Base):
    __tablename__ = "duty_schedule"

    id: Mapped[uuid.UUID] = uuid_pk()
    date: Mapped[date] = mapped_column(Date, nullable=False)
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id"), nullable=False
    )
    is_full_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = now_tz()

    __table_args__ = (
        CheckConstraint(
            "is_full_day = TRUE OR (start_time IS NOT NULL AND end_time IS NOT NULL)",
            name="partial_day_requires_times"
        ),
        CheckConstraint(
            "start_time IS NULL OR end_time IS NULL OR end_time > start_time",
            name="valid_duty_time_range"
        ),
    )

    # Relationships
    person: Mapped["Person"] = relationship(back_populates="duty_entries")
