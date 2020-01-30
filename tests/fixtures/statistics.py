# -*- coding: utf-8 -*-
#
# Copyright (C) Pootle contributors.
#
# This file is a part of the Pootle project. It is distributed under the GPL3
# or later license. See the LICENSE file for a copy of the license and the
# AUTHORS file for copyright and authorship information.

import pytest


@pytest.fixture
def anon_submission_unit(nobody, store0):
    from django.utils import timezone
    from pootle_statistics.models import SubmissionTypes

    anon = nobody
    unit = store0.units.first()
    old_target = unit.target
    old_state = unit.state
    unit.target_f = "Updated %s" % old_target
    unit._target_updated = True

    unit.store.record_submissions(
        unit, old_target, old_state, timezone.now(), anon, SubmissionTypes.NORMAL
    )
    unit.save()


@pytest.fixture
def quality_check_submission(admin):
    from pootle_store.constants import TRANSLATED
    from pootle_store.models import QualityCheck

    # create a sub with quality check info
    qc_filter = dict(
        unit__state=TRANSLATED,
        unit__store__translation_project__project__disabled=False,
    )
    qc = QualityCheck.objects.filter(**qc_filter).first()
    unit = qc.unit
    unit.toggle_qualitycheck(qc.id, True, admin)
    return unit.submission_set.filter(quality_check__gt=0).first()
