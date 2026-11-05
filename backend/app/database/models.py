"""
Consolidated database models registration.
Importing all models here ensures that Base.metadata has the complete schema
for migrations and table creation.
"""

from backend.app.database.base import Base, GUID
from backend.app.modules.institutions.models import Institution, InstitutionDepartment
from backend.app.modules.sources.models import Source, SourceRun, SourceDiscovery
from backend.app.modules.documents.models import Document, DocumentVersion, DocumentPage
from backend.app.modules.provisions.models import Provision
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.modules.obligations.models import Obligation, ObligationApplicability
from backend.app.modules.analysis.models import DocumentAnalysis, AnalysisClaim, ClaimCitation, AnalysisLease
from backend.app.modules.identity.models import User, UserProfile
from backend.app.modules.organizations.models import Organization, Department, OrganizationMember
from backend.app.modules.compliance.models import ComplianceRegister, ComplianceItem, ComplianceTask, TaskEvidence, TaskReview, TaskEvent
from backend.app.modules.audit.models import AuditEvent

__all__ = [
    "Base",
    "GUID",
    "Institution",
    "InstitutionDepartment",
    "Source",
    "SourceRun",
    "SourceDiscovery",
    "Document",
    "DocumentVersion",
    "DocumentPage",
    "Provision",
    "DocumentRelationship",
    "Obligation",
    "ObligationApplicability",
    "DocumentAnalysis",
    "AnalysisClaim",
    "ClaimCitation",
    "AnalysisLease",
    "User",
    "UserProfile",
    "Organization",
    "Department",
    "OrganizationMember",
    "ComplianceRegister",
    "ComplianceItem",
    "ComplianceTask",
    "TaskEvidence",
    "TaskReview",
    "TaskEvent",
    "AuditEvent",
]
