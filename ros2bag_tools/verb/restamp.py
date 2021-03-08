# Copyright 2020 AIT Austrian Institute of Technology GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime
import os
from ros2bag.api import print_error
from ros2bag.verb import VerbExtension
from rclpy.time import Time
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def get_rosbag_options(path, serialization_format='cdr'):
    import rosbag2_py
    storage_options = rosbag2_py.StorageOptions(uri=path, storage_id='sqlite3')
    converter_options = rosbag2_py.ConverterOptions(
        input_serialization_format=serialization_format,
        output_serialization_format=serialization_format)
    return storage_options, converter_options


class RestampVerb(VerbExtension):
    """ros2 bag cut."""

    def add_arguments(self, parser, _cli_name):  # noqa: D102
        parser.add_argument(
            'bag_file', help='input bag file')
        parser.add_argument(
            '-o', '--output',
            help='destination of the bagfile to create, \
            defaults to a timestamped folder in the current directory')
        parser.add_argument(
            '-s', '--in-storage',
            help='storage identifier to be used for the input bag, defaults to "sqlite3"')
        parser.add_argument(
            '--out-storage', default='sqlite3',
            help='storage identifier to be used for the output bag, defaults to "sqlite3"')
        parser.add_argument(
            '-f', '--serialization-format', default='',
            help='rmw serialization format in which the messages are saved, defaults to the'
                 ' rmw currently in use')

    def main(self, *, args):  # noqa: D102
        bag_file = args.bag_file
        if not os.path.exists(bag_file):
            return print_error("bag file '{}' does not exist!".format(bag_file))

        uri = args.output or datetime.now().strftime('rosbag2_%Y_%m_%d-%H_%M_%S')

        if os.path.isdir(uri):
            return print_error("Output folder '{}' already exists.".format(uri))

        from rosbag2_py import (
            SequentialReader,
            SequentialWriter,
            StorageOptions,
            ConverterOptions,
        )

        reader = SequentialReader()
        in_storage_options, in_converter_options = get_rosbag_options(bag_file)
        if args.in_storage:
            in_storage_options.storage = args.in_storage
        reader.open(in_storage_options, in_converter_options)

        writer = SequentialWriter()
        out_storage_options = StorageOptions(uri=uri, storage_id=args.out_storage)
        out_converter_options = ConverterOptions(
            input_serialization_format=args.serialization_format,
            output_serialization_format=args.serialization_format)
        writer.open(out_storage_options, out_converter_options)

        topic_type_map = {}
        type_map = {}
        for topic_metadata in reader.get_all_topics_and_types():
            topic_type = topic_metadata.type
            if topic_type not in type_map:
                try:
                    type_map[topic_type] = get_message(topic_type)
                except (AttributeError, ModuleNotFoundError, ValueError):
                    raise RuntimeError(f"Cannot load message type '{topic_type}'")
            topic_type_map[topic_metadata.name] = type_map[topic_type]
            writer.create_topic(topic_metadata)

        while reader.has_next():
            (topic, data, t) = reader.read_next()
            msg = deserialize_message(data, type_map[topic])
            if msg.header:
                t = Time.from_msg(msg.header.stamp).nanoseconds
            writer.write(topic, data, t)

        del writer
        del reader

        if os.path.isdir(uri) and not os.listdir(uri):
            os.rmdir(uri)
