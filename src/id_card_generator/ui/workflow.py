"""Single source of truth for the ID Studio workflow.

Every screen (navigation ribbon, page headers, page footers, status bar)
derives its labels and ordering from the stage table below, so the application
always presents one coherent pipeline:

    Hub -> Data Source -> Photo Library -> Templates -> Template Designer
         -> Generate -> Review -> Export

``requires`` lists the stages that should be finished before a stage becomes
meaningful; the shell uses it to enable or disable navigation entries and to
show the "what is missing" hint on gated steps.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from id_card_generator.core.constants import WorkflowStep


@dataclass(frozen=True)
class WorkflowStage:
    """Description of a single stage of the production pipeline."""

    step: WorkflowStep
    title: str
    subtitle: str
    tab: str
    nav_label: str
    requires: Tuple[WorkflowStep, ...] = field(default_factory=tuple)

    @property
    def is_pipeline(self) -> bool:
        """True when the stage belongs to the linear production pipeline."""
        return self.step != WorkflowStep.DASHBOARD


# Ribbon identifiers (kept as plain strings to avoid import cycles).
TAB_HUB = "hub"
TAB_DATA_SOURCE = "data_source"
TAB_PHOTOS = "photos"
TAB_TEMPLATES = "templates"
TAB_DESIGNER = "designer"
TAB_GENERATE = "generate"
TAB_REVIEW = "review"
TAB_EXPORT = "export"
TAB_SETTINGS = "settings"


STAGES: Tuple[WorkflowStage, ...] = (
    WorkflowStage(
        step=WorkflowStep.DASHBOARD,
        title="Project Hub",
        subtitle="Start a new project, reopen a recent one, or jump into a workspace.",
        tab=TAB_HUB,
        nav_label="Hub",
    ),
    WorkflowStage(
        step=WorkflowStep.DATA_SOURCE,
        title="Data Source",
        subtitle="Connect a spreadsheet and map its columns to card fields.",
        tab=TAB_DATA_SOURCE,
        nav_label="Data Source",
    ),
    WorkflowStage(
        step=WorkflowStep.PHOTOS,
        title="Photo Library",
        subtitle="Match record photos and resolve missing images.",
        tab=TAB_PHOTOS,
        nav_label="Photo Library",
        requires=(WorkflowStep.DATA_SOURCE,),
    ),
    WorkflowStage(
        step=WorkflowStep.TEMPLATES,
        title="Templates",
        subtitle="Pick or build the card layout for this project.",
        tab=TAB_TEMPLATES,
        nav_label="Templates",
    ),
    WorkflowStage(
        step=WorkflowStep.CANVAS_EDITOR,
        title="Template Designer",
        subtitle="Place and style every element on the card canvas.",
        tab=TAB_DESIGNER,
        nav_label="Template Designer",
        requires=(WorkflowStep.TEMPLATES,),
    ),
    WorkflowStage(
        step=WorkflowStep.GENERATE,
        title="Generate Cards",
        subtitle="Render one card per record into the staging area.",
        tab=TAB_GENERATE,
        nav_label="Generate",
        requires=(WorkflowStep.DATA_SOURCE, WorkflowStep.CANVAS_EDITOR),
    ),
    WorkflowStage(
        step=WorkflowStep.REVIEW,
        title="Review Cards",
        subtitle="Approve or flag each generated card before export.",
        tab=TAB_REVIEW,
        nav_label="Review",
        requires=(WorkflowStep.GENERATE,),
    ),
    WorkflowStage(
        step=WorkflowStep.EXPORT,
        title="Export Cards",
        subtitle="Write every approved card as an individual image file.",
        tab=TAB_EXPORT,
        nav_label="Export",
        requires=(WorkflowStep.REVIEW,),
    ),
    WorkflowStage(
        step=WorkflowStep.SETTINGS,
        title="Settings",
        subtitle="Theme, output defaults and application preferences.",
        tab=TAB_SETTINGS,
        nav_label="Settings",
    ),
)

# Ordered list of the linear production pipeline (hub and settings excluded).
PIPELINE: Tuple[WorkflowStep, ...] = tuple(
    stage.step for stage in STAGES if stage.is_pipeline and stage.step != WorkflowStep.SETTINGS
)

_BY_STEP: Dict[WorkflowStep, WorkflowStage] = {stage.step: stage for stage in STAGES}


def stage_for(step: WorkflowStep) -> WorkflowStage:
    """Return the stage description for a workflow step."""
    return _BY_STEP[step]


def title_for(step: WorkflowStep) -> str:
    """Return the display title of a step."""
    return _BY_STEP[step].title


def subtitle_for(step: WorkflowStep) -> str:
    """Return the display subtitle of a step."""
    return _BY_STEP[step].subtitle


def tab_for(step: WorkflowStep) -> str:
    """Return the ribbon entry a step belongs to."""
    return _BY_STEP[step].tab


def pipeline_position(step: WorkflowStep) -> Tuple[int, int]:
    """Return the ``(position, total)`` of a step inside the production pipeline."""
    if step in PIPELINE:
        return (PIPELINE.index(step) + 1, len(PIPELINE))
    return (0, len(PIPELINE))


def step_badge(step: WorkflowStep) -> str:
    """Return the badge text shown in page footers, e.g. ``Step 3 of 7``."""
    position, total = pipeline_position(step)
    if position == 0:
        return "Project Hub"
    return f"Step {position} of {total}"


def next_step(step: WorkflowStep) -> Optional[WorkflowStep]:
    """Return the step that follows ``step`` in the pipeline."""
    if step not in PIPELINE:
        return None
    index = PIPELINE.index(step)
    if index + 1 >= len(PIPELINE):
        return None
    return PIPELINE[index + 1]


def previous_step(step: WorkflowStep) -> Optional[WorkflowStep]:
    """Return the step that precedes ``step`` in the pipeline."""
    if step not in PIPELINE:
        return None
    index = PIPELINE.index(step)
    if index == 0:
        return None
    return PIPELINE[index - 1]


def missing_requirements(
    step: WorkflowStep,
    completed: Dict[WorkflowStep, bool],
) -> List[WorkflowStage]:
    """Return the stages that still block ``step`` from being meaningfully used."""
    stage = _BY_STEP[step]
    return [
        _BY_STEP[req]
        for req in stage.requires
        if not completed.get(req, False)
    ]


def step_for_tab(tab: str) -> Optional[WorkflowStep]:
    """Return the step a ribbon entry belongs to."""
    for stage in STAGES:
        if stage.tab == tab:
            return stage.step
    return None


def step_completed(
    step: WorkflowStep,
    completed: Dict[WorkflowStep, bool],
) -> bool:
    """Return True when a step and all of its prerequisites are finished."""
    if not completed.get(step, False):
        return False
    return all(completed.get(req, False) for req in _BY_STEP[step].requires)


def footer_labels(step: WorkflowStep) -> Tuple[Optional[str], Optional[str], str]:
    """Return the ``(back label, next label, badge)`` for a page footer.

    The back / next labels are derived from the pipeline so every page
    navigates with the same wording and the same order.
    """
    previous = previous_step(step)
    following = next_step(step)

    if step == WorkflowStep.EXPORT:
        next_label = "Back to Hub"
    elif following is not None:
        next_label = _BY_STEP[following].nav_label
    else:
        next_label = None

    if previous is not None:
        back_label = _BY_STEP[previous].nav_label
    elif step != WorkflowStep.DASHBOARD:
        # The first pipeline step still offers a way back to the hub.
        back_label = _BY_STEP[WorkflowStep.DASHBOARD].nav_label
    else:
        back_label = None
    return back_label, next_label, step_badge(step)


def page_header_text(step: WorkflowStep) -> Tuple[str, str, str]:
    """Return the ``(badge, title, subtitle)`` for a page header."""
    stage = _BY_STEP[step]
    return (step_badge(step), stage.title, stage.subtitle)
