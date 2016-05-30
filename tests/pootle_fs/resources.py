#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) Pootle contributors.
#
# This file is a part of the Pootle project. It is distributed under the GPL3
# or later license. See the LICENSE file for a copy of the license and the
# AUTHORS file for copyright and authorship information.

from uuid import uuid4

import pytest

from django.utils.functional import cached_property

from pootle_fs.models import StoreFS
from pootle_fs.resources import (
    FSProjectResources, FSProjectStateResources)
from pootle_project.models import Project
from pootle_store.models import Store


@pytest.mark.django_db
def test_project_resources_instance():
    project = Project.objects.get(code="project0")
    resources = FSProjectResources(project)
    assert resources.project == project
    assert str(resources) == "<FSProjectResources(Project 0)>"


@pytest.mark.django_db
def test_project_resources_stores():
    project = Project.objects.get(code="project0")
    stores = Store.objects.filter(
        translation_project__project=project)
    assert list(FSProjectResources(project).stores) == list(stores)
    # mark some Stores obsolete - should still show
    store_count = stores.count()
    assert store_count
    for store in stores:
        store.makeobsolete()
    assert list(FSProjectResources(project).stores) == list(stores)
    assert stores.count() == store_count


@pytest.mark.django_db
def test_project_resources_trackable_stores(project0_fs_resources):
    project = project0_fs_resources
    stores = Store.objects.filter(
        translation_project__project=project)
    # only stores that are not obsolete and do not have an
    # exiting StoreFS should be trackable
    trackable = stores.filter(obsolete=False).order_by("pk")
    trackable = trackable.filter(fs__isnull=True)
    assert (
        list(FSProjectResources(project).trackable_stores.order_by("pk"))
        == list(trackable))
    for store in FSProjectResources(project).trackable_stores:
        try:
            fs = store.fs.get()
        except StoreFS.DoesNotExist:
            fs = None
        assert fs is None
        assert store.obsolete is False


@pytest.mark.django_db
def test_project_resources_tracked(project0_fs_resources):
    project = project0_fs_resources
    assert (
        list(FSProjectResources(project).tracked.order_by("pk"))
        == list(StoreFS.objects.filter(project=project).order_by("pk")))
    # this includes obsolete stores
    assert FSProjectResources(project).tracked.filter(
        store__obsolete=True).exists()


@pytest.mark.django_db
def test_project_resources_synced(project0_fs_resources):
    project = project0_fs_resources
    synced = StoreFS.objects.filter(project=project).order_by("pk")
    obsoleted = synced.filter(store__obsolete=True).first()
    obsoleted.last_sync_hash = "FOO"
    obsoleted.last_sync_revision = 23
    obsoleted.save()
    active = synced.exclude(store__obsolete=True).first()
    active.last_sync_hash = "FOO"
    active.last_sync_revision = 23
    active.save()
    synced = synced.exclude(last_sync_revision__isnull=True)
    synced = synced.exclude(last_sync_hash__isnull=True)
    assert (
        list(FSProjectResources(project).synced.order_by("pk"))
        == list(synced))
    assert FSProjectResources(project).synced.count() == 2


@pytest.mark.django_db
def test_project_resources_unsynced(project0_fs_resources):
    project = project0_fs_resources
    for store_fs in FSProjectResources(project).tracked:
        store_fs.last_sync_hash = "FOO"
        store_fs.last_sync_revision = 23
        store_fs.save()
    unsynced = StoreFS.objects.filter(project=project).order_by("pk")
    obsoleted = unsynced.filter(store__obsolete=True).first()
    obsoleted.last_sync_hash = None
    obsoleted.last_sync_revision = None
    obsoleted.save()
    active = unsynced.exclude(store__obsolete=True).first()
    active.last_sync_hash = None
    active.last_sync_revision = None
    active.save()
    unsynced = unsynced.filter(last_sync_revision__isnull=True)
    unsynced = unsynced.filter(last_sync_hash__isnull=True)
    assert (
        list(FSProjectResources(project).unsynced.order_by("pk"))
        == list(unsynced))
    assert FSProjectResources(project).unsynced.count() == 2


class DummyPlugin(object):

    def __init__(self, project):
        self.project = project

    @cached_property
    def resources(self):
        return FSProjectResources(self.project)

    def reload(self):
        if "resources" in self.__dict__:
            del self.__dict__["resources"]


@pytest.mark.django_db
def test_fs_state_resources(project0_fs_resources):
    project = project0_fs_resources
    plugin = DummyPlugin(project)
    state_resources = FSProjectStateResources(plugin)
    assert state_resources.resources is plugin.resources
    # resources are cached on state and plugin
    plugin.reload()
    assert state_resources.resources is not plugin.resources
    state_resources.reload()
    assert state_resources.resources is plugin.resources


def _add_store_fs(store, fs_path, synced=False):
    if synced:
        return StoreFS.objects.create(
            store=store,
            path=fs_path,
            last_sync_hash=uuid4().hex,
            last_sync_revision=store.get_max_unit_revision())
    return StoreFS.objects.create(
        store=store,
        path=fs_path)


@pytest.mark.django_db
def test_fs_state_trackable(fs_path_queries):
    plugin, (qfilter, pootle_path, fs_path) = fs_path_queries
    qs = Store.objects.filter(
        translation_project__project=plugin.project)
    if qfilter is False:
        qs = qs.none()
    elif qfilter:
        qs = qs.filter(qfilter)
    trackable = FSProjectStateResources(
        plugin,
        pootle_path=pootle_path,
        fs_path=fs_path).trackable_stores
    assert (
        sorted(trackable, key=lambda item: item[0].pk)
        == [(store, plugin.get_fs_path(store.pootle_path))
            for store in list(qs.order_by("pk"))])


@pytest.mark.django_db
def test_fs_state_trackable_store_paths(fs_path_queries):
    plugin, (qfilter, pootle_path, fs_path) = fs_path_queries
    qs = Store.objects.filter(
        translation_project__project=plugin.project)
    if qfilter is False:
        qs = qs.none()
    elif qfilter:
        qs = qs.filter(qfilter)
    resources = FSProjectStateResources(plugin)
    assert (
        sorted(
            (store.pootle_path, fs_path)
            for store, fs_path
            in resources.trackable_stores)
        == sorted(resources.trackable_store_paths.items()))


@pytest.mark.django_db
def test_fs_state_trackable_tracked(project0_dummy_plugin):
    plugin = project0_dummy_plugin
    project = plugin.project
    stores = Store.objects.filter(translation_project__project=project)
    store = stores[0]
    # the Store is not trackable if its got a StoreFS
    _add_store_fs(
        store,
        plugin.get_fs_path(store.pootle_path))
    trackable = FSProjectStateResources(plugin).trackable_stores
    qs = stores.exclude(pootle_path=store.pootle_path)
    assert (
        sorted(trackable, key=lambda item: item[0].pk)
        == [(s, plugin.get_fs_path(s.pootle_path))
            for s in list(qs.order_by("pk"))])


@pytest.mark.django_db
def test_fs_state_synced(fs_path_queries):
    plugin, (qfilter, pootle_path, fs_path) = fs_path_queries
    resources = FSProjectStateResources(plugin)
    for trackable in resources.trackable_stores:
        _add_store_fs(*trackable, synced=True)
    qs = StoreFS.objects.filter(project=plugin.project)
    if qfilter is False:
        qs = qs.none()
    elif qfilter:
        qs = qs.filter(qfilter)
    synced = FSProjectStateResources(
        plugin,
        pootle_path=pootle_path,
        fs_path=fs_path).synced
    assert (
        list(synced.order_by("pk"))
        == list(qs.order_by("pk")))


@pytest.mark.django_db
def test_fs_state_synced_staged(project0_dummy_plugin):
    plugin = project0_dummy_plugin
    resources = FSProjectStateResources(plugin)
    store_fs = _add_store_fs(*resources.trackable_stores[0], synced=True)
    assert resources.synced.count() == 1
    # synced does not include any that are staged rm/merge
    store_fs.staged_for_merge = True
    store_fs.save()
    assert resources.synced.count() == 0
    store_fs.staged_for_merge = False
    store_fs.staged_for_removal = True
    store_fs.save()
    assert resources.synced.count() == 0
    store_fs.staged_for_removal = False
    store_fs.save()
    assert resources.synced.count() == 1


@pytest.mark.django_db
def test_fs_state_unsynced(fs_path_queries):
    plugin, (qfilter, pootle_path, fs_path) = fs_path_queries
    resources = FSProjectStateResources(plugin)
    for trackable in resources.trackable_stores:
        _add_store_fs(*trackable)
    qs = StoreFS.objects.filter(project=plugin.project)
    if qfilter is False:
        qs = qs.none()
    elif qfilter:
        qs = qs.filter(qfilter)
    unsynced = FSProjectStateResources(
        plugin,
        pootle_path=pootle_path,
        fs_path=fs_path).unsynced
    assert (
        list(unsynced.order_by("pk"))
        == list(qs.order_by("pk")))


@pytest.mark.django_db
def test_fs_state_unsynced_staged(project0_dummy_plugin):
    plugin = project0_dummy_plugin
    resources = FSProjectStateResources(plugin)
    store_fs = _add_store_fs(*resources.trackable_stores[0])
    assert resources.unsynced.count() == 1
    # unsynced does not include any that are staged rm/merge
    store_fs.staged_for_merge = True
    store_fs.save()
    assert resources.unsynced.count() == 0
    store_fs.staged_for_merge = False
    store_fs.staged_for_removal = True
    store_fs.save()
    assert resources.unsynced.count() == 0
    store_fs.staged_for_removal = False
    store_fs.save()
    assert resources.unsynced.count() == 1


@pytest.mark.django_db
def test_fs_state_tracked(fs_path_queries):
    plugin, (qfilter, pootle_path, fs_path) = fs_path_queries
    resources = FSProjectStateResources(plugin)
    for trackable in resources.trackable_stores:
        _add_store_fs(*trackable)
    qs = StoreFS.objects.filter(project=plugin.project)
    if qfilter is False:
        qs = qs.none()
    elif qfilter:
        qs = qs.filter(qfilter)
    tracked = FSProjectStateResources(
        plugin,
        pootle_path=pootle_path,
        fs_path=fs_path).tracked
    assert (
        list(tracked.order_by("pk"))
        == list(qs.order_by("pk")))


@pytest.mark.django_db
def test_fs_state_tracked_paths(fs_path_queries):
    plugin, (qfilter, pootle_path, fs_path) = fs_path_queries
    resources = FSProjectStateResources(plugin)
    for trackable in resources.trackable_stores:
        _add_store_fs(*trackable)
    qs = StoreFS.objects.filter(project=plugin.project)
    if qfilter is False:
        qs = qs.none()
    elif qfilter:
        qs = qs.filter(qfilter)
    resources = FSProjectStateResources(plugin)
    assert (
        sorted(resources.tracked.values_list("path", "pootle_path"))
        == sorted(resources.tracked_paths.items()))


@pytest.mark.django_db
def test_fs_state_pootle_changed(fs_path_queries):
    plugin, (qfilter, pootle_path, fs_path) = fs_path_queries
    resources = FSProjectStateResources(plugin)
    for trackable in resources.trackable_stores:
        _add_store_fs(*trackable, synced=True)
    assert list(
        FSProjectStateResources(
            plugin,
            pootle_path=pootle_path,
            fs_path=fs_path).pootle_changed) == []
    stores = Store.objects.filter(
        translation_project__project=plugin.project)
    for store in stores.all():
        unit = store.units.first()
        unit.target = "%s FOO!" % store.name
        unit.save()
    qs = StoreFS.objects.filter(project=plugin.project)
    if qfilter is False:
        qs = qs.none()
    elif qfilter:
        qs = qs.filter(qfilter)
    resources = FSProjectStateResources(
        plugin,
        pootle_path=pootle_path,
        fs_path=fs_path)
    assert (
        sorted(resources.pootle_changed.values_list("pk", flat=True))
        == sorted(qs.values_list("pk", flat=True)))


@pytest.mark.django_db
def test_fs_state_found_file_paths(fs_path_queries):
    plugin, (qfilter, pootle_path, fs_path) = fs_path_queries
    resources = FSProjectStateResources(
        plugin, pootle_path=pootle_path, fs_path=fs_path)
    assert (
        resources.found_file_paths
        == sorted(
            (pp, hash("%s::%s::/fs%s" % (fs_path, pootle_path, pp)))
            for pp
            in resources.resources.stores.values_list(
                "pootle_path", flat=True)))
