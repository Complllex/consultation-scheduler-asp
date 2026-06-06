from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import clingo
from sqlalchemy.orm import Session

from app.models.consultation_request import ConsultationRequest
from app.models.consultation_request_blocked_slot import ConsultationRequestBlockedSlot
from app.models.consultation_request_group import ConsultationRequestGroup
from app.models.discipline import Discipline
from app.models.schedule_slot import ScheduleSlot
from app.models.schedule_slot_teacher import ScheduleSlotTeacher
from app.models.teacher_generation_run import TeacherGenerationRun
from app.models.teacher_generation_run_request import TeacherGenerationRunRequest
from app.models.teacher_generation_run_variant import TeacherGenerationRunVariant
from app.models.teacher_generation_run_variant_slot import TeacherGenerationRunVariantSlot
from app.models.teacher_manual_busy_slot import TeacherManualBusySlot
from dataclasses import asdict, dataclass

MODEL_PATH = Path(__file__).resolve().parent.parent / "asp" / "model.lp"


@dataclass
class BatchVariant:
    variant_number: int
    comment: str
    placements: Dict[int, List[Tuple[int, int, str]]]

@dataclass
class BatchVariantMetrics:
    variant_number: int
    rank: int
    is_best: bool
    hard_conflicts_count: int
    first_pair_violations_count: int
    last_pair_violations_count: int
    preferred_day_violations_count: int
    total_window_penalty: int
    fallback_day_without_classes_used: bool
    summary_score: tuple[int, int, int]
    placements: Dict[int, List[Tuple[int, int, str]]]
    placements_pretty: List[Dict[str, object]]
    window_penalty_breakdown: List[Dict[str, object]]
    explanation: str

@dataclass
class BatchRunStats:
    requests_count: int
    candidate_slots_count: int
    fallback_day_without_classes_used: bool

def _slot_weeks(week_type: str) -> set[str]:
    if week_type == "both":
        return {"num", "den"}
    return {week_type}

def _week_type_label(week_type: str) -> str:
    if week_type == "num":
        return "числитель"
    if week_type == "den":
        return "знаменатель"
    return "обе недели"

def _expand_conflict(slot: Tuple[int, int, str]) -> set[Tuple[int, int, str]]:
    day, pair, week_type = slot
    if week_type == "both":
        return {(day, pair, "both"), (day, pair, "num"), (day, pair, "den")}
    return {(day, pair, week_type), (day, pair, "both")}


def _is_forbidden(
    candidate: Tuple[int, int, str],
    forbidden_slots: set[Tuple[int, int, str]],
) -> bool:
    candidate_expanded = _expand_conflict(candidate)

    for forbidden in forbidden_slots:
        if forbidden in candidate_expanded:
            return True
        if candidate in _expand_conflict(forbidden):
            return True

    return False


def _build_run_requests(db: Session, run_id: int) -> List[ConsultationRequest]:
    request_ids = (
        db.query(TeacherGenerationRunRequest.request_id)
        .filter(TeacherGenerationRunRequest.run_id == run_id)
        .all()
    )
    ids = [request_id for (request_id,) in request_ids]
    if not ids:
        return []

    return (
        db.query(ConsultationRequest)
        .filter(ConsultationRequest.id.in_(ids))
        .order_by(ConsultationRequest.id.asc())
        .all()
    )


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


def OLD_build_group_busy_slots(db: Session, group_id: int) -> set[Tuple[int, int, str]]:
    rows = (
        db.query(ScheduleSlot.day, ScheduleSlot.pair_number, ScheduleSlot.week_type)
        .filter(ScheduleSlot.group_id == group_id)
        .all()
    )
    return {(day, pair, week_type) for day, pair, week_type in rows}

def _build_group_busy_slots(db: Session, group_id: int) -> set[Tuple[int, int, str]]:
    rows = (
        db.query(
            ScheduleSlot.day,
            ScheduleSlot.pair_number,
            ScheduleSlot.week_type,
            Discipline.full_name,
            Discipline.abbr,
            Discipline.short_name,
        )
        .outerjoin(Discipline, Discipline.id == ScheduleSlot.discipline_id)
        .filter(ScheduleSlot.group_id == group_id)
        .all()
    )

    result = set()

    for day, pair, week_type, full_name, abbr, short_name in rows:
        if _is_placeholder_discipline(full_name, abbr, short_name):
            continue
        result.add((day, pair, week_type))

    return result

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

def _all_groups_have_classes_for_candidate_day(
    candidate: Tuple[int, int, str],
    all_group_day_week_presences: List[Dict[Tuple[int, str], bool]],
) -> bool:
    day, _, week_type = candidate

    for week in _slot_weeks(week_type):
        for group_day_week_presence in all_group_day_week_presences:
            if not group_day_week_presence.get((day, week), False):
                return False

    return True

def _build_group_day_week_presence(db: Session, group_id: int) -> Dict[Tuple[int, str], bool]:
    rows = (
        db.query(
            ScheduleSlot.day,
            ScheduleSlot.week_type,
            Discipline.full_name,
            Discipline.abbr,
            Discipline.short_name,
        )
        .outerjoin(Discipline, Discipline.id == ScheduleSlot.discipline_id)
        .filter(ScheduleSlot.group_id == group_id)
        .all()
    )

    result: Dict[Tuple[int, str], bool] = {}

    for day, week_type, full_name, abbr, short_name in rows:
        if _is_placeholder_discipline(full_name, abbr, short_name):
            continue

        for week in _slot_weeks(week_type):
            result[(day, week)] = True

    return result

def _build_group_day_pair_counts(db: Session, group_id: int) -> Dict[Tuple[int, str], set[int]]:
    rows = (
        db.query(
            ScheduleSlot.day,
            ScheduleSlot.pair_number,
            ScheduleSlot.week_type,
            Discipline.full_name,
            Discipline.abbr,
            Discipline.short_name,
        )
        .outerjoin(Discipline, Discipline.id == ScheduleSlot.discipline_id)
        .filter(ScheduleSlot.group_id == group_id)
        .all()
    )

    result: Dict[Tuple[int, str], set[int]] = {}

    for day, pair_number, week_type, full_name, abbr, short_name in rows:
        if _is_placeholder_discipline(full_name, abbr, short_name):
            continue

        for week in _slot_weeks(week_type):
            key = (day, week)
            if key not in result:
                result[key] = set()
            result[key].add(pair_number)

    return result

def _build_approved_consultation_busy_slots_for_teacher(
    db: Session, teacher_id: int
) -> set[Tuple[int, int, str]]:
    approved_requests = (
        db.query(ConsultationRequest)
        .filter(ConsultationRequest.status == "approved")
        .filter(ConsultationRequest.teacher_id == teacher_id)
        .all()
    )

    request_ids = [request.id for request in approved_requests]
    if not request_ids:
        return set()

    selected_variant_ids = (
        db.query(TeacherGenerationRunVariant.id)
        .join(
            TeacherGenerationRunRequest,
            TeacherGenerationRunRequest.run_id == TeacherGenerationRunVariant.run_id,
        )
        .filter(TeacherGenerationRunRequest.request_id.in_(request_ids))
        .filter(TeacherGenerationRunVariant.status == "selected")
        .distinct()
        .all()
    )

    variant_ids = [variant_id for (variant_id,) in selected_variant_ids]
    if not variant_ids:
        return set()

    rows = (
        db.query(
            TeacherGenerationRunVariantSlot.day,
            TeacherGenerationRunVariantSlot.pair_number,
            TeacherGenerationRunVariantSlot.week_type,
        )
        .filter(TeacherGenerationRunVariantSlot.run_variant_id.in_(variant_ids))
        .all()
    )

    return {(day, pair, week_type) for day, pair, week_type in rows}


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


def _has_teacher_classes_for_candidate_day(
    candidate: Tuple[int, int, str],
    teacher_day_week_presence: Dict[Tuple[int, str], bool],
) -> bool:
    day, _, week_type = candidate

    for week in _slot_weeks(week_type):
        if not teacher_day_week_presence.get((day, week), False):
            return False

    return True


def _build_teacher_day_week_presence(
    db: Session,
    teacher_id: int,
) -> Dict[Tuple[int, str], bool]:

    result: Dict[Tuple[int, str], bool] = {}

    base_rows = (
        db.query(ScheduleSlot.day, ScheduleSlot.week_type)
        .join(ScheduleSlotTeacher, ScheduleSlotTeacher.slot_id == ScheduleSlot.id)
        .filter(ScheduleSlotTeacher.teacher_id == teacher_id)
        .all()
    )

    manual_rows = (
        db.query(TeacherManualBusySlot.day, TeacherManualBusySlot.week_type)
        .filter(TeacherManualBusySlot.teacher_id == teacher_id)
        .all()
    )

    approved_rows = list(_build_approved_consultation_busy_slots_for_teacher(db, teacher_id))

    for day, week_type in list(base_rows) + list(manual_rows):
        for week in _slot_weeks(week_type):
            result[(day, week)] = True

    for day, _, week_type in approved_rows:
        for week in _slot_weeks(week_type):
            result[(day, week)] = True

    return result


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


def _build_day_week_pair_map(
    slots: set[Tuple[int, int, str]],
) -> Dict[Tuple[int, str], set[int]]:
    result: Dict[Tuple[int, str], set[int]] = {}

    for day, pair_number, week_type in slots:
        for week in _slot_weeks(week_type):
            key = (day, week)
            if key not in result:
                result[key] = set()
            result[key].add(pair_number)

    return result


def _calc_entity_window_penalty_details(
    pair_number: int,
    existing_pairs: set[int],
) -> tuple[int, str]:
    if not existing_pairs:
        return 0, "у сущности нет занятий в этот день"

    if (pair_number - 1) in existing_pairs or (pair_number + 1) in existing_pairs:
        return 0, "слот примыкает к существующей паре"

    min_pair = min(existing_pairs)
    max_pair = max(existing_pairs)

    if min_pair < pair_number < max_pair:
        return 4, "слот создаёт окно внутри диапазона занятий"

    return 2, "слот не примыкает и образует отдельный край диапазона"


def _build_slot_penalties(
    teacher_busy_map: Dict[Tuple[int, str], set[int]],
    all_group_busy_maps: List[tuple[int, Dict[Tuple[int, str], set[int]]]],
    all_group_day_week_presences: List[Dict[Tuple[int, str], bool]],
    candidates: List[Tuple[int, int, str]],
) -> tuple[
    Dict[Tuple[int, int, str], int],
    Dict[Tuple[int, int, str], List[Dict[str, object]]],
]:
    penalties: Dict[Tuple[int, int, str], int] = {}
    penalty_details: Dict[Tuple[int, int, str], List[Dict[str, object]]] = {}

    for candidate in candidates:
        day, pair_number, week_type = candidate
        candidate_weeks = _slot_weeks(week_type)

        total_penalty = 0
        details: List[Dict[str, object]] = []

        for week in candidate_weeks:
            teacher_pairs = teacher_busy_map.get((day, week), set())
            teacher_penalty, teacher_reason = _calc_entity_window_penalty_details(
                pair_number,
                teacher_pairs,
            )
            total_penalty += teacher_penalty
            details.append(
                {
                    "entity_type": "teacher",
                    "entity_id": None,
                    "week": week,
                    "existing_pairs": sorted(teacher_pairs),
                    "penalty": teacher_penalty,
                    "reason": teacher_reason,
                }
            )

            for group_id, group_busy_map in all_group_busy_maps:
                group_pairs = group_busy_map.get((day, week), set())
                group_penalty, group_reason = _calc_entity_window_penalty_details(
                    pair_number,
                    group_pairs,
                )
                total_penalty += group_penalty
                details.append(
                    {
                        "entity_type": "group",
                        "entity_id": group_id,
                        "week": week,
                        "existing_pairs": sorted(group_pairs),
                        "penalty": group_penalty,
                        "reason": group_reason,
                    }
                )

        empty_day_penalty = _calc_group_empty_day_penalty(
            candidate,
            all_group_day_week_presences,
        )
        if empty_day_penalty > 0:
            total_penalty += empty_day_penalty
            details.append(
                {
                    "entity_type": "group_empty_day",
                    "entity_id": None,
                    "week": None,
                    "existing_pairs": [],
                    "penalty": empty_day_penalty,
                    "reason": "у части групп в этот день нет занятий",
                }
            )

        penalties[candidate] = total_penalty
        penalty_details[candidate] = details

    return penalties, penalty_details


def _build_request_candidates(
    db: Session,
    request: ConsultationRequest,
    teacher_busy: set[Tuple[int, int, str]],
    teacher_day_week_presence: Dict[Tuple[int, str], bool],
    relax_avoid_day_without_classes: bool = False,
) -> tuple[
    List[Tuple[int, int, str]],
    set[Tuple[int, int, str]],
    set[int],
    Dict[Tuple[int, int, str], int],
    Dict[Tuple[int, int, str], List[Dict[str, object]]],
]:
    request_group_ids = _build_request_group_ids(db, request.id)
    if not request_group_ids:
        return [], set(), set(), {}, {}

    all_group_busy: set[Tuple[int, int, str]] = set()
    all_vuc_days: set[int] = set()
    all_group_day_pair_counts: List[Dict[Tuple[int, str], set[int]]] = []
    all_group_busy_maps: List[tuple[int, Dict[Tuple[int, str], set[int]]]] = []
    all_group_day_week_presences: List[Dict[Tuple[int, str], bool]] = []

    for group_id in request_group_ids:
        group_busy = _build_group_busy_slots(db, group_id)
        all_group_busy |= group_busy
        all_vuc_days |= _build_group_vuc_days(db, group_id)
        all_group_day_pair_counts.append(_build_group_day_pair_counts(db, group_id))
        all_group_busy_maps.append((group_id, _build_day_week_pair_map(group_busy)))
        all_group_day_week_presences.append(_build_group_day_week_presence(db, group_id))

    blocked_slots = _build_blocked_slots(db, request.id)
    allowed_week_types = _allowed_week_types(request.week_preference)

    candidates: List[Tuple[int, int, str]] = []

    for day in range(1, 7):
        if request.excluded_day is not None and day == request.excluded_day:
            continue

        if day in all_vuc_days:
            continue

        for pair in range(1, 8):
            for week_type in allowed_week_types:
                candidate = (day, pair, week_type)

                if request.avoid_day_without_classes and not relax_avoid_day_without_classes:
                    if not _has_teacher_classes_for_candidate_day(
                        candidate,
                        teacher_day_week_presence,
                    ):
                        continue

                if _is_forbidden(candidate, blocked_slots):
                    continue
                if _is_forbidden(candidate, teacher_busy):
                    continue
                if _is_forbidden(candidate, all_group_busy):
                    continue
                if _is_forbidden_by_sixth_pair_rule(candidate, all_group_day_pair_counts):
                    continue

                candidates.append(candidate)

    teacher_busy_map = _build_day_week_pair_map(teacher_busy)
    slot_penalties, slot_penalty_details = _build_slot_penalties(
        teacher_busy_map=teacher_busy_map, 
        all_group_busy_maps=all_group_busy_maps,
        all_group_day_week_presences=all_group_day_week_presences,
        candidates=candidates,
    )

    return candidates, all_group_busy, all_vuc_days, slot_penalties, slot_penalty_details

def _calc_group_empty_day_penalty(
    candidate: Tuple[int, int, str],
    all_group_day_week_presences: List[Dict[Tuple[int, str], bool]],
) -> int:
    day, _, week_type = candidate
    weeks = _slot_weeks(week_type)

    penalty = 0

    for group_day_week_presence in all_group_day_week_presences:
        missing_for_candidate = False

        for week in weeks:
            if not group_day_week_presence.get((day, week), False):
                missing_for_candidate = True
                break

        if missing_for_candidate:
            penalty += 4

    return penalty

def _build_batch_instance(
    db: Session,
    teacher_id: int,
    requests: List[ConsultationRequest],
    relax_avoid_day_without_classes: bool = False,
) -> tuple[
    str,
    BatchRunStats,
    Dict[int, Dict[Tuple[int, int, str], int]],
    Dict[int, Dict[Tuple[int, int, str], List[Dict[str, object]]]],
]:
    lines: List[str] = []

    teacher_busy = _build_teacher_busy_slots(db, teacher_id)
    teacher_busy |= _build_teacher_manual_busy_slots(db, teacher_id)
    teacher_busy |= _build_approved_consultation_busy_slots_for_teacher(db, teacher_id)

    teacher_day_week_presence = _build_teacher_day_week_presence(db, teacher_id)

    total_candidate_slots = 0
    slot_penalty_maps: Dict[int, Dict[Tuple[int, int, str], int]] = {}

    slot_penalty_detail_maps: Dict[
        int,
        Dict[Tuple[int, int, str], List[Dict[str, object]]]
    ] = {}

    for day, pair, week_type in teacher_busy:
        lines.append(f"busy_teacher({day},{pair},{week_type}).")

    for request in requests:
        rid = request.id

        lines.append(f"request({rid}).")
        lines.append(f"request_count({rid},{request.consultations_count}).")

        if request.avoid_day_without_classes:
            lines.append(f"avoid_day_without_classes({rid}).")

        if request.avoid_first_pair:
            lines.append(f"avoid_first_pair({rid}).")

        if request.avoid_last_pair:
            lines.append(f"avoid_last_pair({rid}).")

        if request.excluded_day is not None:
            lines.append(f"excluded_day({rid},{request.excluded_day}).")

        if request.preferred_day is not None:
            lines.append(f"preferred_day({rid},{request.preferred_day}).")

        candidates, all_group_busy, all_vuc_days, slot_penalties, slot_penalty_details = _build_request_candidates(
            db=db,
            request=request,
            teacher_busy=teacher_busy,
            teacher_day_week_presence=teacher_day_week_presence,
            relax_avoid_day_without_classes=relax_avoid_day_without_classes,
        )

        total_candidate_slots += len(candidates)
        slot_penalty_maps[rid] = slot_penalties
        slot_penalty_detail_maps[rid] = slot_penalty_details

        for day in all_vuc_days:
            lines.append(f"vuc_day({rid},{day}).")

        for day, pair, week_type in all_group_busy:
            lines.append(f"busy_group({rid},{day},{pair},{week_type}).")

        for day, pair, week_type in candidates:
            lines.append(f"candidate_slot({rid},{day},{pair},{week_type}).")

        for (day, pair, week_type), weight in slot_penalties.items():
            lines.append(f"slot_penalty({rid},{day},{pair},{week_type},{weight}).")

    stats = BatchRunStats(
        requests_count=len(requests),
        candidate_slots_count=total_candidate_slots,
        fallback_day_without_classes_used=relax_avoid_day_without_classes,
    )

    return "\n".join(lines), stats, slot_penalty_maps, slot_penalty_detail_maps

def _evaluate_batch_variant(
    variant: BatchVariant,
    requests: List[ConsultationRequest],
    slot_penalty_maps: Dict[int, Dict[Tuple[int, int, str], int]],
    slot_penalty_detail_maps: Dict[int, Dict[Tuple[int, int, str], List[Dict[str, object]]]],
    fallback_day_without_classes_used: bool,
) -> BatchVariantMetrics:
    request_map = {request.id: request for request in requests}

    first_pair_violations_count = 0
    last_pair_violations_count = 0
    preferred_day_violations_count = 0
    total_window_penalty = 0

    placements_pretty: List[Dict[str, object]] = []
    window_penalty_breakdown: List[Dict[str, object]] = []

    for request_id, slots in variant.placements.items():
        request = request_map.get(request_id)
        if not request:
            continue

        pretty_slots = []

        for day, pair_number, week_type in slots:
            if request.avoid_first_pair and pair_number == 1:
                first_pair_violations_count += 1

            if request.avoid_last_pair and pair_number == 7:
                last_pair_violations_count += 1

            if request.preferred_day is not None and day != request.preferred_day:
                preferred_day_violations_count += 1

            slot_penalty = slot_penalty_maps.get(request_id, {}).get(
                (day, pair_number, week_type), 0
            )
            total_window_penalty += slot_penalty

            pretty_slots.append(
                {
                    "day": day,
                    "pair_number": pair_number,
                    "week_type": week_type,
                    "week_type_label": _week_type_label(week_type),
                }
            )

            window_penalty_breakdown.append(
                {
                    "request_id": request_id,
                    "day": day,
                    "pair_number": pair_number,
                    "week_type": week_type,
                    "week_type_label": _week_type_label(week_type),
                    "penalty": slot_penalty,
                    "details": slot_penalty_detail_maps.get(request_id, {}).get(
                        (day, pair_number, week_type), []
                    ),
                }
            )

        placements_pretty.append(
            {
                "request_id": request_id,
                "slots": pretty_slots,
            }
        )

    hard_conflicts_count = 0

    summary_score = (
        preferred_day_violations_count,
        first_pair_violations_count + last_pair_violations_count,
        total_window_penalty,
    )

    explanation_parts = [
        "варианты сравниваются лексикографически по вектору [нарушения предпочитаемого дня, нарушения крайних пар, штраф за окна]"
    ]

    if first_pair_violations_count == 0 and last_pair_violations_count == 0:
        explanation_parts.append("не нарушает ограничения по первой и последней паре")
    else:
        explanation_parts.append(
            f"имеет нарушения по крайним парам: "
            f"{first_pair_violations_count + last_pair_violations_count}"
        )

    if preferred_day_violations_count == 0:
        explanation_parts.append("не нарушает предпочтительный день")
    else:
        explanation_parts.append(
            f"имеет нарушений предпочтительного дня: {preferred_day_violations_count}"
        )

    explanation_parts.append(f"суммарный штраф за окна: {total_window_penalty}")

    if fallback_day_without_classes_used:
        explanation_parts.append(
            "использован fallback по ограничению 'не ставить в день без занятий'"
        )
    else:
        explanation_parts.append(
            "fallback по ограничению 'не ставить в день без занятий' не использовался"
        )

    return BatchVariantMetrics(
        variant_number=variant.variant_number,
        rank=0,
        is_best=False,
        hard_conflicts_count=hard_conflicts_count,
        first_pair_violations_count=first_pair_violations_count,
        last_pair_violations_count=last_pair_violations_count,
        preferred_day_violations_count=preferred_day_violations_count,
        total_window_penalty=total_window_penalty,
        fallback_day_without_classes_used=fallback_day_without_classes_used,
        summary_score=summary_score,
        placements=variant.placements,
        placements_pretty=placements_pretty,
        window_penalty_breakdown=window_penalty_breakdown,
        explanation="; ".join(explanation_parts),
    )

def _solve_batch_variants(instance_text: str, max_variants: int = 3) -> List[BatchVariant]:
    result: List[BatchVariant] = []
    excluded_variants: List[Tuple[Tuple[int, int, int, str], ...]] = []

    for _ in range(max_variants):
        ctl = clingo.Control(
            [
                "--opt-mode=opt",
                "--models=0",
            ]
        )
        ctl.load(str(MODEL_PATH))
        ctl.add("base", [], instance_text)

        if excluded_variants:
            exclusion_rules = []
            for frozen in excluded_variants:
                atoms = [
                    f"place({request_id},{day},{pair},{week_type})"
                    for request_id, day, pair, week_type in frozen
                ]
                exclusion_rules.append(":- " + ", ".join(atoms) + ".")
            ctl.add("base", [], "\n".join(exclusion_rules))

        ctl.ground([("base", [])])

        best_placements: Dict[int, List[Tuple[int, int, str]]] | None = None
        best_frozen: Tuple[Tuple[int, int, int, str], ...] | None = None

        with ctl.solve(yield_=True) as handle:
            for model in handle:
                placements: Dict[int, List[Tuple[int, int, str]]] = {}

                for symbol in model.symbols(shown=True):
                    if symbol.name != "place" or len(symbol.arguments) != 4:
                        continue

                    request_id = symbol.arguments[0].number
                    day = symbol.arguments[1].number
                    pair = symbol.arguments[2].number
                    week_type = str(symbol.arguments[3])

                    placements.setdefault(request_id, []).append((day, pair, week_type))

                normalized = []
                for request_id, slots in placements.items():
                    for day, pair, week_type in sorted(slots, key=lambda x: (x[0], x[1], x[2])):
                        normalized.append((request_id, day, pair, week_type))

                normalized.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
                frozen = tuple(normalized)

                for request_id in placements:
                    placements[request_id].sort(key=lambda x: (x[0], x[1], x[2]))

                best_placements = placements
                best_frozen = frozen

        if not best_placements or not best_frozen:
            break

        excluded_variants.append(best_frozen)

        result.append(
            BatchVariant(
                variant_number=len(result) + 1,
                comment="Общий вариант по всем активным заявкам преподавателя",
                placements=best_placements,
            )
        )

    return result

def _is_placeholder_discipline(
    full_name: str | None,
    abbr: str | None,
    short_name: str | None,
) -> bool:
    for value in (full_name, abbr, short_name):
        if not value:
            continue
        normalized = value.strip().lower()
        if normalized == "самостоятельная работа":
            return True
    return False

def _is_placeholder_act_type(act_type: str | None) -> bool:
    if not act_type:
        return False

    normalized = act_type.strip().lower()
    return normalized in {
        "самостоятельная работа",
        "ср",
    }

def generate_teacher_batch_variants(
    db: Session,
    run_id: int,
    max_variants: int = 3,
) -> int:
    run = db.query(TeacherGenerationRun).filter(TeacherGenerationRun.id == run_id).first()
    if not run:
        raise ValueError("Generation run not found")

    requests = _build_run_requests(db, run_id)
    if not requests:
        raise ValueError("No requests linked to generation run")

    debug_dir = Path(__file__).resolve().parent.parent / "asp_debug"
    debug_dir.mkdir(exist_ok=True)

    strict_instance_text, strict_stats, strict_slot_penalty_maps, strict_slot_penalty_detail_maps = _build_batch_instance(
        db=db,
        teacher_id=run.teacher_id,
        requests=requests,
        relax_avoid_day_without_classes=False,
    )

    strict_debug_file = debug_dir / f"teacher_run_{run.id}_strict.lp"
    strict_debug_file.write_text(strict_instance_text, encoding="utf-8")

    variants = _solve_batch_variants(
        instance_text=strict_instance_text,
        max_variants=max_variants,
    )

    fallback_used = False
    used_stats = strict_stats
    used_slot_penalty_maps = strict_slot_penalty_maps
    used_slot_penalty_detail_maps = strict_slot_penalty_detail_maps

    if not variants:
        relaxed_instance_text, relaxed_stats, relaxed_slot_penalty_maps, relaxed_slot_penalty_detail_maps = _build_batch_instance(
            db=db,
            teacher_id=run.teacher_id,
            requests=requests,
            relax_avoid_day_without_classes=True,
        )

        relaxed_debug_file = debug_dir / f"teacher_run_{run.id}_relaxed.lp"
        relaxed_debug_file.write_text(relaxed_instance_text, encoding="utf-8")

        variants = _solve_batch_variants(
            instance_text=relaxed_instance_text,
            max_variants=max_variants,
        )
        fallback_used = True
        used_stats = relaxed_stats
        used_slot_penalty_maps = relaxed_slot_penalty_maps
        used_slot_penalty_detail_maps = relaxed_slot_penalty_detail_maps

    variant_metrics = [
        _evaluate_batch_variant(
            variant=variant,
            requests=requests,
            slot_penalty_maps=used_slot_penalty_maps,
            slot_penalty_detail_maps=used_slot_penalty_detail_maps,
            fallback_day_without_classes_used=fallback_used,
        )
        for variant in variants
    ]

    sorted_metrics = sorted(
        variant_metrics,
        key=lambda item: item.summary_score
    )

    rank_map: Dict[int, tuple[int, bool]] = {}
    for index, metric in enumerate(sorted_metrics, start=1):
        rank_map[metric.variant_number] = (index, index == 1)

    enriched_metrics: List[BatchVariantMetrics] = []
    for metric in variant_metrics:
        rank, is_best = rank_map[metric.variant_number]
        enriched_metrics.append(
            BatchVariantMetrics(
                variant_number=metric.variant_number,
                rank=rank,
                is_best=is_best,
                hard_conflicts_count=metric.hard_conflicts_count,
                first_pair_violations_count=metric.first_pair_violations_count,
                last_pair_violations_count=metric.last_pair_violations_count,
                preferred_day_violations_count=metric.preferred_day_violations_count,
                total_window_penalty=metric.total_window_penalty,
                fallback_day_without_classes_used=metric.fallback_day_without_classes_used,
                summary_score=metric.summary_score,
                placements=metric.placements,
                placements_pretty=metric.placements_pretty,
                window_penalty_breakdown=metric.window_penalty_breakdown,
                explanation=metric.explanation,
            )
        )

    metrics_payload = {
        "run_id": run.id,
        "teacher_id": run.teacher_id,
        "requests_count": used_stats.requests_count,
        "candidate_slots_count": used_stats.candidate_slots_count,
        "generated_variants_count": len(variants),
        "fallback_day_without_classes_used": fallback_used,
        "comparison_rule": {
            "type": "lexicographic",
            "summary_score_structure": [
                "preferred_day_violations_count",
                "edge_pair_violations_count",
                "total_window_penalty",
            ],
            "description": (
                "Варианты сравниваются лексикографически: "
                "сначала минимизируются нарушения предпочтительного дня, "
                "затем нарушения по первой/последней паре, "
                "после чего штраф за окна."
            ),
        },
        "variants": [asdict(item) for item in sorted(enriched_metrics, key=lambda x: x.rank)],
    }

    metrics_file = debug_dir / f"teacher_run_{run.id}_metrics.json"
    metrics_file.write_text(
        json.dumps(metrics_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    old_variants = (
        db.query(TeacherGenerationRunVariant)
        .filter(TeacherGenerationRunVariant.run_id == run.id)
        .all()
    )
    old_variant_ids = [variant.id for variant in old_variants]

    if old_variant_ids:
        (
            db.query(TeacherGenerationRunVariantSlot)
            .filter(TeacherGenerationRunVariantSlot.run_variant_id.in_(old_variant_ids))
            .delete(synchronize_session=False)
        )
        (
            db.query(TeacherGenerationRunVariant)
            .filter(TeacherGenerationRunVariant.id.in_(old_variant_ids))
            .delete(synchronize_session=False)
        )

    metrics_map = {item.variant_number: item for item in enriched_metrics}

    for variant in variants:
        metrics = metrics_map.get(variant.variant_number)

        comment = variant.comment or ""
        if metrics:
            prefix = "Лучший вариант" if metrics.is_best else f"Вариант ранга {metrics.rank}"
            comment = (
                f"{prefix}; "
                f"score={metrics.summary_score}; "
                f"first={metrics.first_pair_violations_count}; "
                f"last={metrics.last_pair_violations_count}; "
                f"pref_day={metrics.preferred_day_violations_count}; "
                f"window={metrics.total_window_penalty}"
            )

        if fallback_used:
            comment += "; fallback=day_without_classes"

        db_variant = TeacherGenerationRunVariant(
            run_id=run.id,
            variant_number=variant.variant_number,
            score=None,
            comment=comment,
            status="generated",
        )
        db.add(db_variant)
        db.flush()

        for request_id, slots in variant.placements.items():
            for day, pair_number, week_type in slots:
                db.add(
                    TeacherGenerationRunVariantSlot(
                        run_variant_id=db_variant.id,
                        request_id=request_id,
                        day=day,
                        pair_number=pair_number,
                        week_type=week_type,
                    )
                )

    run.status = "done"
    if fallback_used:
        run.comment = (
            f"Сгенерировано общих вариантов: {len(variants)}; "
            f"candidate_slots={used_stats.candidate_slots_count}; "
            f"использован fallback по условию 'не ставить в день без занятий'"
        )
    else:
        run.comment = (
            f"Сгенерировано общих вариантов: {len(variants)}; "
            f"candidate_slots={used_stats.candidate_slots_count}"
        )

    db.commit()

    return len(variants)