from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import clingo
from sqlalchemy.orm import Session

from app.models.consultation_request import ConsultationRequest
from app.models.consultation_request_blocked_slot import ConsultationRequestBlockedSlot
from app.models.consultation_request_group import ConsultationRequestGroup
from app.models.consultation_variant_slot import ConsultationVariantSlot
from app.models.discipline import Discipline
from app.models.schedule_slot import ScheduleSlot
from app.models.schedule_slot_teacher import ScheduleSlotTeacher
from app.models.teacher_manual_busy_slot import TeacherManualBusySlot

MODEL_PATH = Path(__file__).resolve().parent.parent / "asp" / "model.lp"


@dataclass
class GeneratedVariant:
    variant_number: int
    comment: str
    slots: List[Dict[str, object]]


def _slot_weeks(week_type: str) -> set[str]:
    if week_type == "both":
        return {"num", "den"}
    return {week_type}


def _compatible_week(candidate_week: str, busy_week: str) -> bool:
    return len(_slot_weeks(candidate_week) & _slot_weeks(busy_week)) > 0


def _build_request_group_ids(db: Session, request_id: int) -> List[int]:
    rows = (
        db.query(ConsultationRequestGroup.group_id)
        .filter(ConsultationRequestGroup.request_id == request_id)
        .all()
    )
    return [group_id for (group_id,) in rows]


def _build_teacher_busy_slots(db: Session, teacher_id: int) -> set[Tuple[int, int, str]]:
    rows = (
        db.query(ScheduleSlot.day, ScheduleSlot.pair_number, ScheduleSlot.week_type)
        .join(ScheduleSlotTeacher, ScheduleSlotTeacher.slot_id == ScheduleSlot.id)
        .filter(ScheduleSlotTeacher.teacher_id == teacher_id)
        .all()
    )
    return {(day, pair, week_type) for day, pair, week_type in rows}


def _build_teacher_manual_busy_slots(db: Session, teacher_id: int) -> set[Tuple[int, int, str]]:
    rows = (
        db.query(
            TeacherManualBusySlot.day,
            TeacherManualBusySlot.pair_number,
            TeacherManualBusySlot.week_type,
        )
        .filter(TeacherManualBusySlot.teacher_id == teacher_id)
        .all()
    )
    return {(day, pair, week_type) for day, pair, week_type in rows}


def _build_group_busy_slots(db: Session, group_id: int) -> set[Tuple[int, int, str]]:
    rows = (
        db.query(ScheduleSlot.day, ScheduleSlot.pair_number, ScheduleSlot.week_type)
        .filter(ScheduleSlot.group_id == group_id)
        .all()
    )
    return {(day, pair, week_type) for day, pair, week_type in rows}


def _build_group_vuc_days(db: Session, group_id: int) -> set[int]:
    vuc_days = set()

    try:
        rows = (
            db.query(ScheduleSlot.day)
            .filter(ScheduleSlot.group_id == group_id)
            .filter(ScheduleSlot.is_vuc == True)  # noqa: E712
            .distinct()
            .all()
        )
        vuc_days |= {day for (day,) in rows}
    except Exception:
        pass

    rows = (
        db.query(ScheduleSlot.day)
        .join(Discipline, Discipline.id == ScheduleSlot.discipline_id)
        .filter(ScheduleSlot.group_id == group_id)
        .filter(
            (Discipline.abbr == "ВУЦ")
            | (Discipline.full_name == "ВУЦ")
            | (Discipline.short_name == "ВУЦ")
        )
        .distinct()
        .all()
    )
    vuc_days |= {day for (day,) in rows}

    return vuc_days


def _build_group_day_max_pairs(db: Session, group_id: int) -> Dict[Tuple[int, str], int]:

    rows = (
        db.query(ScheduleSlot.day, ScheduleSlot.pair_number, ScheduleSlot.week_type)
        .filter(ScheduleSlot.group_id == group_id)
        .all()
    )

    result: Dict[Tuple[int, str], int] = {}

    for day, pair_number, week_type in rows:
        for week in _slot_weeks(week_type):
            key = (day, week)
            result[key] = max(result.get(key, 0), pair_number)

    return result

def _build_group_day_pair_counts(db: Session, group_id: int) -> Dict[Tuple[int, str], set[int]]:

    rows = (
        db.query(ScheduleSlot.day, ScheduleSlot.pair_number, ScheduleSlot.week_type)
        .filter(ScheduleSlot.group_id == group_id)
        .all()
    )

    result: Dict[Tuple[int, str], set[int]] = {}

    for day, pair_number, week_type in rows:
        for week in _slot_weeks(week_type):
            key = (day, week)
            if key not in result:
                result[key] = set()
            result[key].add(pair_number)

    return result

def _build_approved_consultation_busy_slots_for_teacher(
    db: Session, teacher_id: int, exclude_request_id: int
) -> set[Tuple[int, int, str]]:
    approved_requests = (
        db.query(ConsultationRequest)
        .filter(ConsultationRequest.status == "approved")
        .filter(ConsultationRequest.selected_variant_id.isnot(None))
        .filter(ConsultationRequest.teacher_id == teacher_id)
        .filter(ConsultationRequest.id != exclude_request_id)
        .all()
    )

    busy: set[Tuple[int, int, str]] = set()

    for req in approved_requests:
        slots = (
            db.query(
                ConsultationVariantSlot.day,
                ConsultationVariantSlot.pair_number,
                ConsultationVariantSlot.week_type,
            )
            .filter(ConsultationVariantSlot.variant_id == req.selected_variant_id)
            .all()
        )
        for day, pair, week_type in slots:
            busy.add((day, pair, week_type))

    return busy


def _build_blocked_slots(db: Session, request_id: int) -> set[Tuple[int, int, str]]:
    rows = (
        db.query(
            ConsultationRequestBlockedSlot.day,
            ConsultationRequestBlockedSlot.pair_number,
            ConsultationRequestBlockedSlot.week_type,
        )
        .filter(ConsultationRequestBlockedSlot.request_id == request_id)
        .all()
    )
    return {(day, pair, week_type) for day, pair, week_type in rows}


def _build_teacher_days_with_classes(db: Session, teacher_id: int) -> set[int]:
    base_days = (
        db.query(ScheduleSlot.day)
        .join(ScheduleSlotTeacher, ScheduleSlotTeacher.slot_id == ScheduleSlot.id)
        .filter(ScheduleSlotTeacher.teacher_id == teacher_id)
        .distinct()
        .all()
    )

    manual_days = (
        db.query(TeacherManualBusySlot.day)
        .filter(TeacherManualBusySlot.teacher_id == teacher_id)
        .distinct()
        .all()
    )

    return {day for (day,) in base_days} | {day for (day,) in manual_days}


def _expand_conflict(slot: Tuple[int, int, str]) -> set[Tuple[int, int, str]]:
    day, pair, week_type = slot
    if week_type == "both":
        return {(day, pair, "both"), (day, pair, "num"), (day, pair, "den")}
    return {(day, pair, week_type), (day, pair, "both")}


def _is_forbidden(candidate: Tuple[int, int, str], forbidden_slots: set[Tuple[int, int, str]]) -> bool:
    candidate_expanded = _expand_conflict(candidate)

    for forbidden in forbidden_slots:
        if forbidden in candidate_expanded:
            return True
        if candidate in _expand_conflict(forbidden):
            return True

    return False


def _allowed_week_types(week_preference: str) -> tuple[str, ...]:
    if week_preference == "num":
        return ("num",)
    if week_preference == "den":
        return ("den",)
    return ("both",)


def _is_forbidden_by_sixth_pair_rule(
    candidate: Tuple[int, int, str],
    all_group_day_pair_counts: List[Dict[Tuple[int, str], set[int]]],
) -> bool:
    day, pair_number, week_type = candidate
    candidate_weeks = _slot_weeks(week_type)

    for group_day_pair_counts in all_group_day_pair_counts:
        for week in candidate_weeks:
            occupied_pairs = group_day_pair_counts.get((day, week), set())


            if len(occupied_pairs) >= 5 and pair_number not in occupied_pairs:
                return True

    return False


def _build_day_week_pair_map(slots: set[Tuple[int, int, str]]) -> Dict[Tuple[int, str], set[int]]:
    result: Dict[Tuple[int, str], set[int]] = {}

    for day, pair_number, week_type in slots:
        for week in _slot_weeks(week_type):
            key = (day, week)
            if key not in result:
                result[key] = set()
            result[key].add(pair_number)

    return result


def _calc_entity_window_penalty(
    pair_number: int,
    existing_pairs: set[int],
) -> int:
    if not existing_pairs:
        return 0

    if (pair_number - 1) in existing_pairs or (pair_number + 1) in existing_pairs:
        return 0

    min_pair = min(existing_pairs)
    max_pair = max(existing_pairs)

    if min_pair < pair_number < max_pair:
        return 4

    return 2


def _build_slot_penalties(
    teacher_busy: set[Tuple[int, int, str]],
    all_group_busy_maps: List[Dict[Tuple[int, str], set[int]]],
    teacher_busy_map: Dict[Tuple[int, str], set[int]],
    candidates: List[Tuple[int, int, str]],
) -> Dict[Tuple[int, int, str], int]:
    penalties: Dict[Tuple[int, int, str], int] = {}

    for candidate in candidates:
        day, pair_number, week_type = candidate
        candidate_weeks = _slot_weeks(week_type)

        total_penalty = 0

        for week in candidate_weeks:
            teacher_pairs = teacher_busy_map.get((day, week), set())
            total_penalty += _calc_entity_window_penalty(pair_number, teacher_pairs)

            for group_busy_map in all_group_busy_maps:
                group_pairs = group_busy_map.get((day, week), set())
                total_penalty += _calc_entity_window_penalty(pair_number, group_pairs)

        penalties[candidate] = total_penalty

    return penalties


def _build_candidate_slots(
    request: ConsultationRequest,
    teacher_busy: set[Tuple[int, int, str]],
    all_group_busy: set[Tuple[int, int, str]],
    blocked_slots: set[Tuple[int, int, str]],
    teacher_days: set[int],
    all_vuc_days: set[int],
    all_group_day_max_pairs: List[Dict[Tuple[int, str], int]],
) -> List[Tuple[int, int, str]]:
    candidates: List[Tuple[int, int, str]] = []
    allowed_week_types = _allowed_week_types(request.week_preference)

    for day in range(1, 7):
        if request.avoid_day_without_classes and day not in teacher_days:
            continue

        if request.excluded_day is not None and day == request.excluded_day:
            continue

        if day in all_vuc_days:
            continue

        for pair in range(1, 8):
            for week_type in allowed_week_types:
                candidate = (day, pair, week_type)

                if _is_forbidden(candidate, blocked_slots):
                    continue
                if _is_forbidden(candidate, teacher_busy):
                    continue
                if _is_forbidden(candidate, all_group_busy):
                    continue
                if _is_forbidden_by_sixth_pair_rule(candidate, all_group_day_pair_counts):
                    continue

                candidates.append(candidate)

    return candidates


def _build_instance_facts(
    request: ConsultationRequest,
    teacher_days: set[int],
    teacher_busy: set[Tuple[int, int, str]],
    all_group_busy: set[Tuple[int, int, str]],
    candidates: List[Tuple[int, int, str]],
    all_vuc_days: set[int],
    slot_penalties: Dict[Tuple[int, int, str], int],
) -> str:
    lines: List[str] = []

    lines.append(f"request_count({request.consultations_count}).")

    if request.avoid_day_without_classes:
        lines.append("avoid_day_without_classes.")

    if request.avoid_first_pair:
        lines.append("avoid_first_pair.")

    if request.avoid_last_pair:
        lines.append("avoid_last_pair.")

    if request.excluded_day is not None:
        lines.append(f"excluded_day({request.excluded_day}).")

    if request.preferred_day is not None:
        lines.append(f"preferred_day({request.preferred_day}).")

    for day in range(1, 7):
        if day not in teacher_days:
            lines.append(f"no_teacher_day({day}).")

    for day in all_vuc_days:
        lines.append(f"vuc_day({day}).")

    for day, pair, week_type in teacher_busy:
        lines.append(f"busy_teacher({day},{pair},{week_type}).")

    for day, pair, week_type in all_group_busy:
        lines.append(f"busy_group({day},{pair},{week_type}).")

    for day, pair, week_type in candidates:
        lines.append(f"candidate_slot({day},{pair},{week_type}).")

    for (day, pair, week_type), weight in slot_penalties.items():
        if weight > 0:
            lines.append(f"slot_penalty({day},{pair},{week_type},{weight}).")

    return "\n".join(lines)


def _solve_variants(instance_text: str, max_variants: int = 3) -> List[List[Tuple[int, int, str]]]:
    ctl = clingo.Control(
        [
            "--opt-mode=optN",
            "--models=0",
        ]
    )
    ctl.load(str(MODEL_PATH))
    ctl.add("base", [], instance_text)
    ctl.ground([("base", [])])

    collected: List[List[Tuple[int, int, str]]] = []
    seen: set[Tuple[Tuple[int, int, str], ...]] = set()

    with ctl.solve(yield_=True) as handle:
        for model in handle:
            slots: List[Tuple[int, int, str]] = []
            for symbol in model.symbols(shown=True):
                if symbol.name != "place" or len(symbol.arguments) != 3:
                    continue

                day = symbol.arguments[0].number
                pair = symbol.arguments[1].number
                week_type = str(symbol.arguments[2])
                slots.append((day, pair, week_type))

            slots.sort(key=lambda x: (x[0], x[1], x[2]))
            frozen = tuple(slots)

            if frozen in seen:
                continue

            seen.add(frozen)
            collected.append(slots)

            if len(collected) >= max_variants:
                break

    return collected


def _build_comment(
    request: ConsultationRequest,
    slots: List[Tuple[int, int, str]],
    teacher_days: set[int],
    all_vuc_days: set[int],
) -> str:
    if not slots:
        return "Вариант без слотов"

    first_day, first_pair, _ = slots[0]
    notes: List[str] = []

    if request.avoid_day_without_classes and first_day not in teacher_days:
        notes.append("в день без занятий")

    if first_day in all_vuc_days:
        notes.append("день ВУЦ")

    if request.avoid_first_pair and any(pair == 1 for _, pair, _ in slots):
        notes.append("есть первая пара")

    if request.avoid_last_pair and any(pair == 7 for _, pair, _ in slots):
        notes.append("есть последняя пара")

    if notes:
        return f"Компромисс: {', '.join(notes)}"

    return f"День {first_day}, пара {first_pair}"


def generate_request_variants_via_asp(
    db: Session, request_id: int, max_variants: int = 3
) -> List[GeneratedVariant]:
    request = db.query(ConsultationRequest).filter(ConsultationRequest.id == request_id).first()
    if not request:
        raise ValueError("Request not found")

    request_group_ids = _build_request_group_ids(db, request.id)
    if not request_group_ids:
        return []

    teacher_busy = _build_teacher_busy_slots(db, request.teacher_id)
    teacher_busy |= _build_teacher_manual_busy_slots(db, request.teacher_id)
    teacher_busy |= _build_approved_consultation_busy_slots_for_teacher(
        db=db,
        teacher_id=request.teacher_id,
        exclude_request_id=request.id,
    )

    all_group_busy: set[Tuple[int, int, str]] = set()
    all_vuc_days: set[int] = set()
    all_group_day_pair_counts: List[Dict[Tuple[int, str], set[int]]] = []
    all_group_busy_maps: List[Dict[Tuple[int, str], set[int]]] = []

    for group_id in request_group_ids:
        group_busy = _build_group_busy_slots(db, group_id)
        all_group_busy |= group_busy
        all_vuc_days |= _build_group_vuc_days(db, group_id)
        all_group_day_pair_counts.append(_build_group_day_pair_counts(db, group_id))
        all_group_busy_maps.append(_build_day_week_pair_map(group_busy))

    blocked_slots = _build_blocked_slots(db, request.id)
    teacher_days = _build_teacher_days_with_classes(db, request.teacher_id)

    candidates = _build_candidate_slots(
        request=request,
        teacher_busy=teacher_busy,
        all_group_busy=all_group_busy,
        blocked_slots=blocked_slots,
        teacher_days=teacher_days,
        all_vuc_days=all_vuc_days,
        all_group_day_max_pairs=all_group_day_max_pairs,
    )

    if len(candidates) < request.consultations_count:
        return []

    teacher_busy_map = _build_day_week_pair_map(teacher_busy)

    slot_penalties = _build_slot_penalties(
        teacher_busy=teacher_busy,
        teacher_busy_map=teacher_busy_map,
        all_group_busy_maps=all_group_busy_maps,
        candidates=candidates,
    )

    instance_text = _build_instance_facts(
        request=request,
        teacher_days=teacher_days,
        teacher_busy=teacher_busy,
        all_group_busy=all_group_busy,
        candidates=candidates,
        all_vuc_days=all_vuc_days,
        slot_penalties=slot_penalties,
    )
    debug_dir = Path(__file__).resolve().parent.parent / "asp_debug"
    debug_dir.mkdir(exist_ok=True)

    debug_file = debug_dir / f"teacher_run_{run.id}.lp"
    debug_file.write_text(instance_text, encoding="utf-8")

    solved_variants = _solve_variants(instance_text=instance_text, max_variants=max_variants)

    variants: List[GeneratedVariant] = []
    for idx, slots in enumerate(solved_variants, start=1):
        variants.append(
            GeneratedVariant(
                variant_number=idx,
                comment=_build_comment(
                    request=request,
                    slots=slots,
                    teacher_days=teacher_days,
                    all_vuc_days=all_vuc_days,
                ),
                slots=[
                    {
                        "day": day,
                        "pair_number": pair,
                        "week_type": week_type,
                    }
                    for day, pair, week_type in slots
                ],
            )
        )

    return variants