"""Generate PDF evidence from session changes data using ReportLab."""

import json
from datetime import datetime
from typing import Any

from arlogi import get_logger
from jinja2 import Environment, FileSystemLoader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = get_logger(__name__)


class SessionChangesPDFGenerator:
    """Generate PDF from session changes data using ReportLab."""

    def __init__(self, template_dir: str = "src/fa/templates"):
        """Initialize the PDF generator."""
        self.styles = getSampleStyleSheet()
        self.env = Environment(loader=FileSystemLoader(template_dir))
        self._add_custom_styles()

    def generate_html(
        self,
        ritm_number: str,
        evidence_number: int,
        username: str,
        session_changes: dict[str, Any],
        section_uid_to_name: dict[str, str] | None = None,
    ) -> str:
        """Render HTML evidence from session changes using Jinja template."""
        if evidence_number not in (1, 2):
            raise ValueError(f"evidence_number must be 1 or 2, got {evidence_number}")

        template = self.env.get_template("session_changes.html")
        domains = self._parse_session_changes(
            session_changes or {}, section_uid_to_name=section_uid_to_name
        )

        # Extract session info from session_changes
        session_info = {}
        if session_changes and "apply_session_trace" in session_changes:
            trace = session_changes["apply_session_trace"]
            if trace and len(trace) > 0:
                session_info = {
                    "session_uid": trace[0].get("session_uid", "N/A"),
                    "sid": trace[0].get("sid", "N/A"),
                }

        return template.render(
            ritm_number=ritm_number,
            evidence_number=evidence_number,
            username=username,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            domains=domains,
            session_info=session_info,
        )

    def _add_custom_styles(self) -> None:
        """Add custom styles for the PDF."""
        # Check if styles already exist before adding
        if "Header" not in self.styles:
            self.styles.add(
                ParagraphStyle(
                    name="Header",
                    parent=self.styles["Heading1"],
                    fontSize=18,
                    textColor=colors.HexColor("#0066cc"),
                    spaceAfter=12,
                )
            )
        if "DomainHeader" not in self.styles:
            self.styles.add(
                ParagraphStyle(
                    name="DomainHeader",
                    parent=self.styles["Heading2"],
                    fontSize=14,
                    textColor=colors.HexColor("#0066cc"),
                    spaceAfter=8,
                    spaceBefore=12,
                )
            )
        if "SectionHeader" not in self.styles:
            self.styles.add(
                ParagraphStyle(
                    name="SectionHeader",
                    parent=self.styles["Heading3"],
                    fontSize=12,
                    textColor=colors.HexColor("#333333"),
                    spaceAfter=6,
                    spaceBefore=8,
                )
            )
        if "BodyText" not in self.styles:
            self.styles.add(
                ParagraphStyle(
                    name="BodyText",
                    parent=self.styles["BodyText"],
                    fontSize=10,
                    spaceAfter=6,
                )
            )
        if "TableCell" not in self.styles:
            self.styles.add(
                ParagraphStyle(
                    name="TableCell",
                    fontSize=8,
                    leading=10,
                    wordWrap="CJK",
                )
            )
        if "TableHeader" not in self.styles:
            self.styles.add(
                ParagraphStyle(
                    name="TableHeader",
                    fontSize=9,
                    leading=11,
                    textColor=colors.white,
                    fontName="Helvetica-Bold",
                )
            )
        if "TableSectionRow" not in self.styles:
            self.styles.add(
                ParagraphStyle(
                    name="TableSectionRow",
                    fontSize=8,
                    leading=13,
                    textColor=colors.HexColor("#333333"),
                    fontName="Helvetica-Bold",
                )
            )

    def generate_pdf(
        self,
        ritm_number: str,
        evidence_number: int,
        username: str,
        session_changes: dict[str, Any],
        section_uid_to_name: dict[str, str] | None = None,
    ) -> bytes:
        """Generate PDF from session changes.

        Args:
            ritm_number: RITM number
            evidence_number: Evidence number (1 or 2)
            username: Current username
            session_changes: Session changes JSON dict from apply response
            section_uid_to_name: Optional mapping of section UIDs to human-readable names

        Returns:
            PDF bytes

        Raises:
            ValueError: If evidence_number not 1/2
            RuntimeError: If PDF generation fails
        """
        if evidence_number not in (1, 2):
            raise ValueError(f"evidence_number must be 1 or 2, got {evidence_number}")

        if not session_changes:
            logger.warning("Empty session_changes provided for PDF generation")
            return self._generate_empty_pdf(ritm_number, evidence_number, username)

        try:
            from io import BytesIO

            from reportlab.lib.pagesizes import landscape

            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=landscape(A4),
                rightMargin=0.75 * inch,
                leftMargin=0.75 * inch,
                topMargin=0.75 * inch,
                bottomMargin=0.75 * inch,
            )

            # Build the PDF content
            story: list[Flowable] = []
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Header
            story.append(
                Paragraph(
                    f"Apply Results: RITM {ritm_number} - Evidence #{evidence_number}",
                    self.styles["Header"],
                )
            )
            story.append(
                Paragraph(f"Generated by: {username} on {timestamp}", self.styles["BodyText"])
            )

            # Add session info if available
            if session_changes and "apply_session_trace" in session_changes:
                trace = session_changes["apply_session_trace"]
                if trace and len(trace) > 0:
                    session_uid = trace[0].get("session_uid", "N/A")
                    story.append(Paragraph(f"Session UID: {session_uid}", self.styles["BodyText"]))

            story.append(Spacer(1, 0.2 * inch))

            # Parse and add content
            domains = self._parse_session_changes(session_changes, section_uid_to_name)

            if not domains:
                story.append(Paragraph("No Changes Recorded", self.styles["DomainHeader"]))
                story.append(
                    Paragraph(
                        "No session changes were captured during the apply operation.",
                        self.styles["BodyText"],
                    )
                )
            else:
                for domain in domains:
                    self._add_domain_section(story, domain)

            # Add raw JSON section
            story.append(PageBreak())
            story.append(Paragraph("Session Changes (Raw JSON)", self.styles["Header"]))
            story.append(Spacer(1, 0.1 * inch))
            json_str = json.dumps(session_changes, indent=2, default=str)
            story.append(Preformatted(json_str, self.styles["Code"]))

            # Build PDF
            doc.build(story)

            pdf_bytes = buffer.getvalue()
            logger.info(
                f"Generated PDF for RITM {ritm_number} evidence #{evidence_number}: "
                f"{len(pdf_bytes)} bytes"
            )

            return pdf_bytes

        except Exception as e:
            logger.error(f"PDF generation failed for RITM {ritm_number}: {e}", exc_info=True)
            raise RuntimeError(f"PDF generation failed: {e}") from e

    def _generate_empty_pdf(
        self,
        ritm_number: str,
        evidence_number: int,
        username: str,
    ) -> bytes:
        """Generate PDF for empty session_changes.

        Args:
            ritm_number: RITM number
            evidence_number: Evidence number
            username: Current username

        Returns:
            PDF bytes with "no changes" message
        """
        from io import BytesIO

        from reportlab.lib.pagesizes import landscape

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        story: list[Flowable] = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        story.append(
            Paragraph(
                f"Apply Results: RITM {ritm_number} - Evidence #{evidence_number}",
                self.styles["Header"],
            )
        )
        story.append(Paragraph(f"Generated by: {username} on {timestamp}", self.styles["BodyText"]))
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph("No Changes Recorded", self.styles["DomainHeader"]))
        story.append(
            Paragraph(
                "No session changes were captured during the apply operation.",
                self.styles["BodyText"],
            )
        )

        doc.build(story)
        return buffer.getvalue()

    def _add_domain_section(self, story: list[Flowable], domain: dict[str, Any]) -> None:
        """Add a domain section to the PDF.

        Args:
            story: The PDF story (list of flowables)
            domain: Domain data with rules and objects
        """
        domain_name = domain.get("name", "Unknown")

        # Domain line: black label + blue value (matches requested HTML-like style)
        story.append(
            Paragraph(
                f'<font color="#222222"><b>Domain:</b></font> '
                f'<font color="#0066cc"><b>{domain_name}</b></font>',
                self.styles["DomainHeader"],
            )
        )

        # Rules grouped by package, each package rendered as its own table block
        rules = domain.get("rules", [])
        if rules:
            from collections import OrderedDict

            packages: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
            for rule in rules:
                pkg_name = str(rule.get("package") or domain.get("package") or "Standard")
                packages.setdefault(pkg_name, []).append(rule)

            for package_name, package_rules in packages.items():
                self._add_package_header(story, package_name)
                self._add_rules_table(story, package_rules)

        # Add objects summary
        objects = domain.get("objects", {})
        self._add_objects_summary(story, objects)

        story.append(Spacer(1, 0.2 * inch))

    def _add_rules_table(self, story: list[Flowable], rules: list[dict[str, Any]]) -> None:
        """Add a rules table grouped by section (layer) to the PDF.

        Layout per table:
          Row 0   : column headers (dark blue, repeated on page break)
          Row N   : section header spanning all columns (yellow)
          Row N+1…: data rows for that section
          (repeat for every additional section)

        Args:
            story: The PDF story (list of flowables)
            rules: List of rule dictionaries; each may have a 'layer' field
        """
        if not rules:
            return

        cell_style = self.styles["TableCell"]
        header_style = self.styles["TableHeader"]
        section_style = self.styles["TableSectionRow"]

        # Column widths to fill landscape A4 (11.69") minus 0.75" margins = 10.19"
        col_widths = [
            0.50 * inch,  # Rule No.
            1.20 * inch,  # Name
            1.50 * inch,  # Source
            1.50 * inch,  # Destination
            1.30 * inch,  # Services & Applications
            0.75 * inch,  # Action
            0.65 * inch,  # Track
            1.10 * inch,  # Targets
            1.69 * inch,  # Comments
        ]
        num_cols = len(col_widths)

        def _col_header_row() -> list[Any]:
            return [
                Paragraph("Rule No.", header_style),
                Paragraph("Name", header_style),
                Paragraph("Source", header_style),
                Paragraph("Destination", header_style),
                Paragraph("Services &amp; Applications", header_style),
                Paragraph("Action", header_style),
                Paragraph("Track", header_style),
                Paragraph("Targets", header_style),
                Paragraph("Comments", header_style),
            ]

        def _section_row(name: str) -> list[Any]:
            return [Paragraph(f"\u25bc  {name}", section_style)] + [""] * (num_cols - 1)

        def _data_row(rule: dict[str, Any]) -> list[Any]:
            return [
                Paragraph(str(rule.get("rule_number", "") or ""), cell_style),
                Paragraph(rule.get("name", ""), cell_style),
                Paragraph(", ".join(rule.get("source", [])), cell_style),
                Paragraph(", ".join(rule.get("destination", [])), cell_style),
                Paragraph(", ".join(rule.get("service", [])), cell_style),
                Paragraph(rule.get("action", ""), cell_style),
                Paragraph(rule.get("track", "") or "Log", cell_style),
                Paragraph(", ".join(rule.get("targets", [])), cell_style),
                Paragraph(rule.get("comments", ""), cell_style),
            ]

        # Group rules by section (layer), preserving insertion order
        from collections import OrderedDict

        sections: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        for rule in rules:
            sec = rule.get("layer") or "Rules"
            sections.setdefault(sec, []).append(rule)

        # Build table rows; track which row indices are section headers
        table_data: list[list[Any]] = [_col_header_row()]  # row 0 = column headers
        section_row_indices: list[int] = []

        for sec_name, sec_rules in sections.items():
            section_row_indices.append(len(table_data))
            table_data.append(_section_row(sec_name))
            for rule in sec_rules:
                table_data.append(_data_row(rule))

        # Base style commands
        style_cmds: list[tuple[Any, ...]] = [
            # Column header row (row 0) – dark blue, white text
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e3f58")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("LEFTPADDING", (0, 0), (-1, 0), 4),
            ("RIGHTPADDING", (0, 0), (-1, 0), 4),
            # Defaults for all rows
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8c8c8")),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("LEFTPADDING", (0, 1), (-1, -1), 4),
            ("RIGHTPADDING", (0, 1), (-1, -1), 4),
        ]

        # Section header rows – yellow band, span all columns
        for idx in section_row_indices:
            style_cmds += [
                ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#ebe5a5")),
                ("SPAN", (0, idx), (-1, idx)),
                ("FONTNAME", (0, idx), (-1, idx), "Helvetica-Bold"),
                ("FONTSIZE", (0, idx), (-1, idx), 10),
                ("TEXTCOLOR", (0, idx), (-1, idx), colors.HexColor("#333333")),
                ("TOPPADDING", (0, idx), (-1, idx), 5),
                ("BOTTOMPADDING", (0, idx), (-1, idx), 5),
                ("LEFTPADDING", (0, idx), (-1, idx), 8),
            ]

        # Alternating row colours for data rows (skip col header + section rows)
        data_row_indices = [i for i in range(1, len(table_data)) if i not in section_row_indices]
        for pos, idx in enumerate(data_row_indices):
            bg = colors.white if pos % 2 == 0 else colors.HexColor("#f0f8ff")
            style_cmds.append(("BACKGROUND", (0, idx), (-1, idx), bg))

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle(style_cmds))

        story.append(table)
        story.append(Spacer(1, 0.1 * inch))

    def _add_package_header(self, story: list[Flowable], package_name: str) -> None:
        """Render package line before each rules table."""
        total_width = sum([0.50, 1.30, 1.70, 1.70, 1.40, 0.80, 0.70, 2.09]) * inch

        pkg_style = ParagraphStyle(
            "PkgCell",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#222222"),
            fontName="Helvetica",
        )

        package_bar = Table(
            [[Paragraph(f"Package: {package_name}", pkg_style)]],
            colWidths=[total_width],
        )
        package_bar.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e6f2ff")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("LINEBEFORE", (0, 0), (0, -1), 4, colors.HexColor("#0066cc")),
                ]
            )
        )
        story.append(package_bar)
        story.append(Spacer(1, 0.08 * inch))

    def _add_objects_summary(
        self, story: list[Flowable], objects: dict[str, dict[str, list[Any]]]
    ) -> None:
        """Add objects summary to the PDF.

        Args:
            story: The PDF story (list of flowables)
            objects: Objects grouped by category (added/modified/deleted) and type
        """
        story.append(Paragraph("Objects Summary", self.styles["SectionHeader"]))

        for category in ["added", "modified", "deleted"]:
            category_objects = objects.get(category, {})
            has_any = any(cat_list for cat_list in category_objects.values())

            if not has_any:
                continue

            # Category header
            category_title = category.capitalize()
            story.append(Paragraph(f"{category_title}:", self.styles["BodyText"]))

            # Object types
            for obj_type, obj_list in category_objects.items():
                if obj_type == "other" and not obj_list:
                    continue
                if not obj_list:
                    continue

                type_name = obj_type.capitalize()
                obj_names = []
                for obj in obj_list:
                    name = obj.get("name", "")
                    if obj_type == "hosts":
                        ip = obj.get("ip", "")
                        obj_names.append(f"{name} ({ip})")
                    elif obj_type == "networks":
                        subnet = obj.get("subnet", "")
                        mask = obj.get("mask", "")
                        obj_names.append(f"{name} ({subnet}/{mask})")
                    elif obj_type == "ranges":
                        first = obj.get("first", "")
                        last = obj.get("last", "")
                        obj_names.append(f"{name} ({first}-{last})")
                    else:
                        obj_names.append(name)

                if obj_names:
                    story.append(
                        Paragraph(f"  {type_name}: {', '.join(obj_names)}", self.styles["BodyText"])
                    )

    def _parse_session_changes(
        self, session_changes: dict[str, Any], section_uid_to_name: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Parse session_changes into structured hierarchy for PDF.

        Args:
            session_changes: Raw session_changes dict from apply response
            section_uid_to_name: Optional mapping of section UIDs to human-readable names

        Returns:
            List of domains, each containing packages, rules, and objects
        """
        if section_uid_to_name is None:
            section_uid_to_name = {}

        logger.debug(f"Parsing session changes with {len(section_uid_to_name)} UID-to-name mappings")
        domains: list[dict[str, Any]] = []

        domain_changes = session_changes.get("domain_changes", {})
        for domain_name, domain_data in domain_changes.items():
            # Extract tasks from domain data
            tasks = domain_data.get("tasks", [])
            if not tasks:
                continue

            for task in tasks:
                task_details = task.get("task-details", [])
                if not task_details:
                    continue

                for detail in task_details:
                    changes = detail.get("changes", [])
                    if not changes:
                        continue

                    for change in changes:
                        operations = change.get("operations", {})
                        added_objects = operations.get("added-objects", [])
                        modified_objects = operations.get("modified-objects", [])
                        deleted_objects = operations.get("deleted-objects", [])

                        # Group objects by type
                        objects_by_type: dict[str, dict[str, list[Any]]] = {
                            "added": {
                                "hosts": [],
                                "networks": [],
                                "ranges": [],
                                "groups": [],
                                "other": [],
                            },
                            "modified": {
                                "hosts": [],
                                "networks": [],
                                "ranges": [],
                                "groups": [],
                                "other": [],
                            },
                            "deleted": {
                                "hosts": [],
                                "networks": [],
                                "ranges": [],
                                "groups": [],
                                "other": [],
                            },
                        }

                        # Separate rules from objects
                        rules: list[dict[str, Any]] = []

                        def resolve_package_name(obj: dict[str, Any]) -> str:
                            """Best-effort package extraction from show-changes payload."""
                            candidates = [
                                ("obj.package", obj.get("package")),
                                ("obj.package-name", obj.get("package-name")),
                                ("obj.policy-package", obj.get("policy-package")),
                                ("obj.rulebase-name", obj.get("rulebase-name")),
                                ("obj.rulebase", obj.get("rulebase")),
                                ("change.package", change.get("package")),
                                ("change.package-name", change.get("package-name")),
                                ("detail.package", detail.get("package")),
                                ("detail.package-name", detail.get("package-name")),
                                ("task.package", task.get("package")),
                                ("task.package-name", task.get("package-name")),
                            ]
                            for field_name, value in candidates:
                                if isinstance(value, str) and value.strip():
                                    return value.strip()
                            return "Standard"

                        def looks_like_uid(value: str) -> bool:
                            """Return True if string looks like a UUID/UID."""
                            import re

                            return bool(
                                re.match(
                                    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
                                    value,
                                )
                            )

                        def resolve_section_name(obj: dict[str, Any]) -> str:
                            """Best-effort access section name extraction.

                            Prefer human-readable names and only fall back to UID when no
                            better value exists.
                            """
                            layer_field = obj.get("layer")
                            if isinstance(layer_field, dict):
                                layer_name = layer_field.get("name")
                                if isinstance(layer_name, str) and layer_name.strip():
                                    return layer_name.strip()

                            candidates = [
                                ("layer-name", obj.get("layer-name")),
                                ("layer_name", obj.get("layer_name")),
                                ("section-name", obj.get("section-name")),
                                ("section_name", obj.get("section_name")),
                                ("access-section-name", obj.get("access-section-name")),
                                ("access-section", obj.get("access-section")),
                                ("layer", obj.get("layer")),
                            ]

                            for field_name, value in candidates:
                                if not isinstance(value, str):
                                    continue
                                candidate = value.strip()
                                if not candidate:
                                    continue

                                # First check if it's a UID that we can resolve
                                if looks_like_uid(candidate) and candidate in section_uid_to_name:
                                    return section_uid_to_name[candidate]

                                if looks_like_uid(candidate):
                                    continue
                                return candidate

                            logger.debug(f"Section name not found for rule {obj.get('name', 'unknown')}, using fallback 'Rules'")
                            return "Rules"

                        # Helper function to process objects
                        def process_objects(objects: list[dict[str, Any]], bucket: str) -> None:
                            """Process objects and categorize them by type."""
                            for obj in objects:
                                obj_type = obj.get("type", "")

                                # Handle access rules separately
                                if obj_type == "access-rule":
                                    install_on = (
                                        obj.get("install-on") or obj.get("install_on") or []
                                    )
                                    targets = []
                                    if isinstance(install_on, list):
                                        for target in install_on:
                                            if isinstance(target, dict):
                                                target_name = target.get("name") or target.get(
                                                    "uid", ""
                                                )
                                                if target_name:
                                                    targets.append(str(target_name))
                                            elif target:
                                                targets.append(str(target))

                                    rule = {
                                        "rule_number": (
                                            obj.get("rule-number")
                                            or obj.get("rule_number")
                                            or obj.get("position", "")
                                        ),
                                        "name": obj.get("name", ""),
                                        "comments": obj.get("comments", ""),
                                        "source": [
                                            s.get("name", s.get("uid", ""))
                                            for s in obj.get("source", [])
                                        ],
                                        "destination": [
                                            d.get("name", d.get("uid", ""))
                                            for d in obj.get("destination", [])
                                        ],
                                        "service": [
                                            s.get("name", s.get("uid", ""))
                                            for s in obj.get("service", [])
                                        ],
                                        "action": obj.get("action", {}).get("name", ""),
                                        "track": obj.get("track", {})
                                        .get("type", {})
                                        .get("name", ""),
                                        "targets": targets,
                                        "layer": resolve_section_name(obj),
                                        "package": resolve_package_name(obj),
                                    }
                                    logger.debug(
                                        f"[TROUBLESHOOT] Rule resolved: layer={rule['layer']}, package={rule['package']}"
                                    )
                                    rules.append(rule)
                                else:
                                    # Handle network objects by type
                                    obj_info = {
                                        "name": obj.get("name", ""),
                                        "uid": obj.get("uid", ""),
                                        "type": obj_type,
                                    }

                                    if obj_type == "host":
                                        obj_info["ip"] = obj.get("ipv4-address", "")
                                        objects_by_type[bucket]["hosts"].append(obj_info)
                                    elif obj_type == "network":
                                        obj_info["subnet"] = obj.get("subnet4", "")
                                        obj_info["mask"] = obj.get("mask-length4", "")
                                        objects_by_type[bucket]["networks"].append(obj_info)
                                    elif obj_type == "address-range":
                                        obj_info["first"] = obj.get("ipv4-address-first", "")
                                        obj_info["last"] = obj.get("ipv4-address-last", "")
                                        objects_by_type[bucket]["ranges"].append(obj_info)
                                    elif obj_type == "network-group":
                                        obj_info["members"] = obj.get("members", [])
                                        objects_by_type[bucket]["groups"].append(obj_info)
                                    else:
                                        objects_by_type[bucket]["other"].append(obj_info)

                        # Process all object categories
                        process_objects(added_objects, "added")
                        process_objects(modified_objects, "modified")
                        process_objects(deleted_objects, "deleted")

                        # Build domain structure
                        domain_entry = {
                            "name": domain_name,
                            "package": "Standard",  # Default package name
                            "rules": rules,
                            "objects": objects_by_type,
                            "has_changes": bool(
                                rules
                                or any(
                                    obj_list
                                    for bucket in objects_by_type.values()
                                    for obj_list in bucket.values()
                                )
                            ),
                        }

                        if domain_entry["has_changes"]:
                            domains.append(domain_entry)

        return domains
