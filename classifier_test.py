
import re
from typing import Literal

from ollama import Client, ResponseError
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    model_validator,
)


# =====================================================
# 1. CONFIGURATION
# =====================================================

MODEL_NAME = "qwen3:8b"

client = Client(
    host="http://127.0.0.1:11434",
    timeout=180,
)

Department = Literal[
    "IT Support",
    "Maintenance",
    "Housekeeping",
    "Warehouse",
    "Purchasing",
    "Reception",
]

RoutingDecision = Literal[
    "ROUTE",
    "CLARIFY",
    "REVIEW",
]


# =====================================================
# 2. STRUCTURED OUTPUT SCHEMAS
# =====================================================

class TicketIssue(BaseModel):

    description: str = Field(min_length=1)

    category: str = Field(min_length=1)

    department: Department | None

    location: str | None

    routing_decision: RoutingDecision

    clarification_question: str | None

    @model_validator(mode="after")
    def validate_issue(self):

        self.description = self.description.strip()
        self.category = self.category.strip()

        if not self.description or not self.category:
            raise ValueError(
                "Issue description and category are required."
            )

        if self.location is not None:
            self.location = self.location.strip() or None

        if self.clarification_question is not None:
            self.clarification_question = (
                self.clarification_question.strip() or None
            )

        # These are not valid physical locations.
        invalid_locations = {
            "النت",
            "الإنترنت",
            "الانترنت",
            "internet",
            "wifi",
            "wi-fi",
            "unknown",
            "not specified",
        }

        if (
            self.location
            and self.location.lower() in invalid_locations
        ):
            self.location = None

        if self.routing_decision == "ROUTE":

            # Never route without a valid department.
            if self.department is None:
                self.routing_decision = "CLARIFY"
                self.clarification_question = (
                    "ممكن توضح المشكلة أكتر؟"
                )
            else:
                self.clarification_question = None

        elif self.routing_decision == "CLARIFY":

            self.department = None

            if not self.clarification_question:
                self.clarification_question = (
                    "ممكن توضح تفاصيل المشكلة أكتر؟"
                )

        elif self.routing_decision == "REVIEW":

            # Review cases must not be routed automatically.
            self.department = None
            self.clarification_question = None

        return self


class TicketClassification(BaseModel):

    issues: list[TicketIssue] = Field(min_length=1)


# =====================================================
# 3. SYSTEM PROMPT
# =====================================================

SYSTEM_PROMPT = """
You are an AI classification engine for
Al Nasaaem Hospital in Egypt.

You analyze INTERNAL EMPLOYEE SERVICE REQUESTS.

Employees communicate using:
- Egyptian Arabic
- Standard Arabic
- English
- Mixed Arabic and English
- Informal spelling and expressions

Your goal is to identify ALL independent issues
mentioned in the employee's message.

IMPORTANT:
One employee message may contain MULTIPLE issues.
Each issue may belong to a DIFFERENT department.

Never ignore a problem simply because another
problem is mentioned in the same message.


=====================================================
AVAILABLE DEPARTMENTS
=====================================================

1. IT Support

Responsibilities:
- Computers and laptops
- Printers and printing problems
- Internet and Wi-Fi
- Network connectivity
- Software problems
- Hospital information system access
- Password and account issues


2. Maintenance

Responsibilities:
- Air conditioning
- Electricity and lighting
- Plumbing and water leaks
- Building maintenance
- Doors, windows, and furniture repairs


3. Housekeeping

Responsibilities:
- Cleaning rooms
- Cleaning corridors
- Floor cleaning
- General housekeeping
- Routine cleaning and waste collection


4. Warehouse

Responsibilities:
- Issuing existing stock
- Stock availability
- Distribution of stored supplies


5. Purchasing

Responsibilities:
- Buying new equipment
- Ordering new supplies
- Procurement requests
- Supplier-related purchasing


6. Reception

Responsibilities:
- Reception administrative operations
- Reception-specific administrative services


These department rules are PROVISIONAL and
intended for a synthetic prototype.


=====================================================
MULTI-ISSUE DETECTION
=====================================================

An employee may describe multiple problems.

You MUST:

1. Read the complete employee message.

2. Identify each independent issue.

3. Create a separate object for each issue.

4. Assign the responsible department to each
   issue independently.

5. Preserve the original meaning.

6. Do not omit any explicitly mentioned issue.

7. Do not create duplicate issues.

8. Do not invent additional problems.

9. Do not infer unmentioned technical causes.

10. Return all issues in the issues array.


EXAMPLE:

Employee:
"النت فاصل والتكييف مش بيبرد"

Expected issues:

Issue 1:
description = "الإنترنت لا يعمل"
category = "Network Issue"
department = "IT Support"
location = null
routing_decision = "ROUTE"

Issue 2:
description = "التكييف لا يبرد"
category = "Air Conditioning Issue"
department = "Maintenance"
location = null
routing_decision = "ROUTE"


=====================================================
LOCATION EXTRACTION
=====================================================

A location is NOT the responsible department.

Extract locations only when explicitly stated.

Examples:

"البرنتر بايظ في الريسبشن"
location = "الريسبشن"

"التكييف مش شغال في الدور التاني"
location = "الدور التاني"

"النت فاصل"
location = null

Never treat these as locations:
- Internet
- Wi-Fi
- Printer
- Computer
- Network

Do not invent room numbers or locations.

If the message describes multiple issues,
only associate a location with an issue when
the employee's message supports that association.

If no location is provided, use null.


=====================================================
AMBIGUOUS REQUESTS
=====================================================

Never guess the type of equipment.

Generic Egyptian Arabic expressions such as:

"الجهاز بايظ"
"الماكينة مش شغالة"
"الحاجة دي مش شغالة"

may refer to many different types of equipment.

If the device or problem cannot be identified
sufficiently to choose a department:

department = null
routing_decision = "CLARIFY"

Ask ONE short question in Egyptian Arabic.

Example:

Employee:
"الجهاز اللي عندنا في الدور التالت مش شغال"

Expected:
description = "جهاز غير محدد لا يعمل"
category = "Unknown Equipment Issue"
department = null
location = "الدور التالت"
routing_decision = "CLARIFY"
clarification_question =
"ممكن توضح نوع الجهاز اللي مش شغال؟"

However:

"جهاز الكمبيوتر مش شغال"

is a clearly identified computer issue.

Do not request unnecessary clarification
when the type of problem is already clear.


=====================================================
ROUTING DECISIONS
=====================================================

Every issue must have ONE routing decision.

ROUTE:

Use when the request is clear and an approved
provisional department can be identified.

A department MUST be provided.


CLARIFY:

Use when important information is missing.

Set department to null.

Provide a short clarification question
in Egyptian Arabic.


REVIEW:

Use when the request may require special
handling or an approved escalation workflow.

Examples include:
- Potential patient safety hazards
- Medical equipment failures
- Oxygen supply issues
- Fire or electrical hazards
- Other potentially dangerous situations

Set department to null.

Do not invent a priority or emergency level.

Do not provide clinical instructions.

This prototype does not implement
real hospital emergency procedures.


=====================================================
ADDITIONAL EXAMPLES
=====================================================

Example 1:

Employee:
"البرنتر عندي في الريسبشن مش بيطبع"

Issue:
description = "الطابعة لا تعمل"
category = "Printer Issue"
department = "IT Support"
location = "الريسبشن"
routing_decision = "ROUTE"
clarification_question = null


Example 2:

Employee:
"في حنفية بتسرب في حمام الدور التاني"

Issue:
description = "تسريب مياه من حنفية"
category = "Plumbing Issue"
department = "Maintenance"
location = "حمام الدور التاني"
routing_decision = "ROUTE"
clarification_question = null


Example 3:

Employee:
"محتاج حد ينضف طرقة العيادات"

Issue:
description = "طلب تنظيف طرقة العيادات"
category = "Cleaning Request"
department = "Housekeeping"
location = "طرقة العيادات"
routing_decision = "ROUTE"
clarification_question = null


Example 4:

Employee:
"الكمبيوتر مش واصله نت"

Issue:
description = "الكمبيوتر لا يتصل بالإنترنت"
category = "Network Issue"
department = "IT Support"
location = null
routing_decision = "ROUTE"
clarification_question = null


=====================================================
OUTPUT REQUIREMENTS
=====================================================

Return JSON matching the provided schema.

The JSON must contain an "issues" array.

Every issue must contain:
- description
- category
- department
- location
- routing_decision
- clarification_question

Use null when a value is unknown.

Never invent information.

Never silently discard an issue.

Never invent priority, deadlines, or commitments.

Do not create tickets or execute actions.
"""


# =====================================================
# 4. BASIC REQUEST SAFETY CHECKS
# =====================================================

def is_generic_broken_device_request(request: str) -> bool:
    """
    Recognizes some single ambiguous equipment requests.

    This is only a supplementary rule.
    It is NOT a complete safety classifier.
    """

    generic_device = re.search(
        r"(?:الجهاز|جهاز|الماكينة|ماكينة)",
        request,
        re.IGNORECASE,
    )

    malfunction = re.search(
        r"(?:مش شغال|مش شغالة|بايظ|بايظة|"
        r"عطلان|عطلانة)",
        request,
        re.IGNORECASE,
    )

    specific_device = re.search(
        r"(?:كمبيوتر|كومبيوتر|لابتوب|لاب توب|"
        r"برنتر|برينتر|طابعة|تكييف|مكيف|"
        r"جهاز أشعة|جهاز اشعة|جهاز تنفس|"
        r"جهاز رسم قلب|ماكينة تصوير)",
        request,
        re.IGNORECASE,
    )

    return bool(
        generic_device
        and malfunction
        and not specific_device
    )


def contains_medical_safety_signal(request: str) -> bool:
    """
    Detect some explicit medical equipment safety signals.
    This is a limited prototype rule, not a comprehensive
    hospital emergency detection system.
    """
    safety_patterns = [
        r"جهاز\s*التنفس",
        r"جهاز\s*تنفس",
        r"الأكسجين",
        r"الاكسجين",
        r"جهاز\s*التخدير",
        r"جهاز\s*الصدمات",
    ]

    return any(
        re.search(pattern, request, re.IGNORECASE)
        for pattern in safety_patterns
    )


# =====================================================
# 5. AI CLASSIFICATION
# =====================================================

def classify_request(employee_request: str):

    if not employee_request.strip():
        print("Error: Employee request is empty.")
        return None

    print("\nAnalyzing employee request...\n")

    try:

        response = client.chat(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": employee_request,
                },
            ],
            format=TicketClassification.model_json_schema(),
            options={
                "temperature": 0,
            },
            think=False,
        )

        result = TicketClassification.model_validate_json(
            response.message.content
        )

        # -------------------------------------------------
        # Conservative guard for a single ambiguous
        # broken-device request.
        #
        # Never apply this blanket override to messages
        # containing multiple issues.
        # -------------------------------------------------

        
        # Safety signals take precedence over ambiguity.
        # Fail closed: never automatically route these cases.
        if contains_medical_safety_signal(employee_request):

            for issue in result.issues:
                issue.department = None
                issue.routing_decision = "REVIEW"
                issue.clarification_question = None

            print(
                "SAFETY FLAG: Manual review/escalation "
                "required. Normal routing disabled."
            )

        elif (
            len(result.issues) == 1
            and is_generic_broken_device_request(
                employee_request
            )
        ):

            issue = result.issues[0]

            # Do not override an existing REVIEW decision.
            if issue.routing_decision != "REVIEW":
                issue.department = None
                issue.category = "Unknown Equipment Issue"
                issue.routing_decision = "CLARIFY"
                issue.clarification_question = (
                    "ممكن توضح نوع الجهاز اللي مش شغال؟"
                )


            issue = result.issues[0]

            issue.department = None
            issue.category = "Unknown Equipment Issue"
            issue.routing_decision = "CLARIFY"
            issue.clarification_question = (
                "ممكن توضح نوع الجهاز اللي مش شغال؟"
            )

        return result

    except ValidationError as error:

        print("Invalid JSON or schema:")
        print(error)

    except ResponseError as error:

        print("Ollama model error:")
        print(error)

    except Exception as error:

        print("Classification error:")
        print(error)

    return None


# =====================================================
# 6. DISPLAY CLASSIFICATION RESULTS
# =====================================================

def display_results(
    employee_request: str,
    result: TicketClassification,
):

    print("=" * 55)
    print("ORIGINAL EMPLOYEE REQUEST")
    print("=" * 55)

    print(employee_request)

    print("\n" + "=" * 55)
    print("AI CLASSIFICATION RESULT")
    print("=" * 55)

    print(result.model_dump_json(indent=2))

    print("\n" + "=" * 55)
    print("ISSUE SUMMARY")
    print("=" * 55)

    print(f"\nDetected issues: {len(result.issues)}")

    for index, issue in enumerate(
        result.issues, start=1
    ):

        print(f"\n--- ISSUE {index} ---")

        print(f"Description: {issue.description}")
        print(f"Category: {issue.category}")
        print(f"Department: {issue.department}")
        print(f"Location: {issue.location}")

        print(
            f"Routing Decision: {issue.routing_decision}"
        )

        if issue.routing_decision == "CLARIFY":

            print(
                "Clarification Question: "
                f"{issue.clarification_question}"
            )

        elif issue.routing_decision == "REVIEW":

            print(
                "Status: Requires human review"
            )

        else:

            print(
                "Status: Eligible for proposed routing"
            )

    print("\n" + "=" * 55)
    print("PROTOTYPE MODE")
    print("=" * 55)

    print(
        "No tickets have been created or routed."
    )


# =====================================================
# 7. MAIN PROGRAM
# =====================================================

def main():

    print("=" * 55)
    print("AL NASAAEM AI HELPDESK")
    print("MULTI-INTENT EMPLOYEE REQUEST CLASSIFIER")
    print("=" * 55)

    employee_request = input(
        "\nاكتب طلب الموظف بالعامية المصرية: "
    ).strip()

    if not employee_request:
        print("Please enter a valid request.")
        return

    result = classify_request(employee_request)

    if result is None:

        print("\nClassification failed.")
        print("Automatic routing is not allowed.")
        return

    display_results(
        employee_request,
        result,
    )


if __name__ == "__main__":
    main()
