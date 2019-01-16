# This file is part of FlameScope, a performance analysis tool created by the
# Netflix cloud performance team. See:
#
#    https://github.com/Netflix/flamescope
#
# Copyright 2018 Netflix, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import json
import copy
from os.path import join
from app.common.fileutil import get_file
from app import config


def trace_event_generate_flame_graph(filename, range_start, range_end, profile=None):
    # TODO: handle CPU time differences, where "E" comes before "B"
    
    root = {'name': 'root', 'value': 0, 'children': []}
    open_partial_slices = {}

    if not profile:
        file_path = join(config.PROFILE_DIR, filename)
        f = get_file(file_path)
        profile = json.load(f)
        f.close()

    def get_child_slice(parent_slice, name):
        for index, child in enumerate(parent_slice['children']):
            if child['name'] == name:
                return parent_slice['children'].pop(index)
        return None

    def insert_slice(parent_slice, new_slice):
        child_slice = get_child_slice(parent_slice, new_slice['name'])
        if child_slice is None:
            child_slice = {'name': new_slice['name'], 'value': 0, 'children': []}
        for child in new_slice['children']:
            insert_slice(child_slice, child)
        child_slice['value'] += new_slice['value']
        parent_slice['children'].append(child_slice)

    def check_thread(pid, tid):
        if pid not in open_partial_slices:
            open_partial_slices[pid] = {}
        if tid not in open_partial_slices[pid]:
            open_partial_slices[pid][tid] = []

    def begin_slice(pid, tid, cat, name, ts, tts):
        check_thread(pid, tid)
        open_partial_slices[pid][tid].append({'pid': pid, 'tid': tid, 'cat': cat, 'name': name, 'ts': ts, 'tts': tts, 'children': []})

    def end_slice(pid, tid, ts, tts):
        partial_slice_count = len(open_partial_slices[pid][tid])
        if partial_slice_count > 0:
            current_slice = open_partial_slices[pid][tid].pop()
            current_slice['dur'] = ts - current_slice['ts']
            current_slice['tdur'] = tts - current_slice['tts']
            if current_slice['dur'] > 0:
                current_slice['value'] = current_slice['tdur'] / current_slice['dur']
            partial_slice_count = len(open_partial_slices[pid][tid])
            if partial_slice_count > 0:
                open_partial_slices[pid][tid][partial_slice_count - 1]['children'].append(current_slice)
            else:
                insert_slice(root, current_slice)
        else:
            raise Exception("end_slice called without an open slice")

    for row in profile:
        if row['ph'] == 'B' or row['ph'] == 'E':
            if row['ph'] == 'B':
                begin_slice(row['pid'], row['tid'], row['cat'], row['name'], row['ts'], row['tts'])
            elif row['ph'] == 'E':
                end_slice(row['pid'], row['tid'], row['ts'], row['tts'])
        elif row['ph'] == 'X':
            if 'dur' in row and row['dur'] > 0 and 'tdur' in row and row['tdur'] > 0:
                begin_slice(row['pid'], row['tid'], row['cat'], row['name'], row['ts'], row['tts'])
                end_slice(row['pid'], row['tid'], row['ts'] + row['dur'], row['tts'] + row['tdur'])

    return root