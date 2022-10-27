from typing import NamedTuple
from kfp.v2 import compiler, dsl
from kfp.v2.dsl import (Artifact,
                        Dataset,
                        Input,
                        Model,
                        Output,
                        Metrics,
                        ClassificationMetrics,
                        component, 
                        OutputPath, 
                        InputPath)

@component(
    packages_to_install=["pandas", "numpy"],
    base_image="python:3.9",
)
def get_dataset(
    url: str,
    train_ds: Output[Dataset],
    test_ds: Output[Dataset],
):
    import pandas as pd
    import numpy as np

    train_data = pd.DataFrame(np.random.random((128, 33)))
    test_data = pd.DataFrame(np.random.random((128, 33)))

    train_data.to_csv(train_ds.path, header=None, index=False)
    test_data.to_csv(test_ds.path, header=None, index=False)


@component(
    base_image="gcr.io/deeplearning-platform-release/tf2-gpu.2-10",
    packages_to_install=["pandas"])
def train(
        train_ds: Input[Dataset],
        model: Output[Model]
    ):

    import pandas as pd
    import tensorflow as tf
    print(tf.__version__)
    print(tf.config.list_physical_devices())

    def get_model():
        # Create a simple model.
        inputs = tf.keras.Input(shape=(32,))
        outputs = tf.keras.layers.Dense(1)(inputs)
        model = tf.keras.Model(inputs, outputs)
        model.compile(optimizer="adam", loss="mean_squared_error")

        return model


    my_model = get_model()
    
    # Train the model.
    train_data = pd.read_csv(train_ds.path).values
    train_input = train_data[:,:-1]
    train_target = train_data[:,-1:]
    my_model.fit(train_input, train_target)

    my_model.save(model.path)


@component(
    base_image="gcr.io/deeplearning-platform-release/tf2-cpu.2-10")
def evaluate(
    test_ds: Input[Dataset],
    model: Input[Model],
    kpi: Output[Metrics]
) -> NamedTuple("output", [("deploy", str)]):
    return ("true",)

@component(
    packages_to_install=['google-cloud-secret-manager', 'requests'],
    base_image="python:3.9")
def serve(
    model: Input[Model]
):
    import os
    import requests

    print(model.path)
    print(os.environ)

    key = os.environ.get("API_KEY", 'API_KEY_NOT_FOUND')
    secret = os.environ.get("API_SECRET", 'API_SECRET_NOT_FOUND')
    url = "https://cloudbuild.googleapis.com/v1/projects/df-data-science-test/triggers/webhook-trigger:webhook?key={key}&secret={secret}".format(key=key, secret=secret)

    path = "df-data-science-test-pipelines/out/364866568815/1982582192601038848/train_-7242054282625679360/model"
    myobj = {'message': {'model_path': path}}
    print(url, myobj)
    x = requests.post(url, json = myobj)
    print(x)


'''
    import os
    import requests
    // from google.cloud import secretmanager

    print(model.path)
    print(os.environ)

    // secret_client = secretmanager.SecretManagerServiceClient()
    // secret_name = f'projects/364866568815/secrets/webhook_trigger-secret-key-1/versions/2'
    // response = secret_client.access_secret_version(request={"name": secret_name})
    // payload = response.payload.data.decode("UTF-8")

    key = os.environ.get("API_KEY", 'API_KEY_NOT_FOUND')
    secret = os.environ.get("API_SECRET", 'API_SECRET_NOT_FOUND')
    url = "https://cloudbuild.googleapis.com/v1/projects/df-data-science-test/triggers/webhook-trigger:webhook?key={key}&secret={secret}".format(key=key, secret=secret)

    // path = model.path.split('/', 1).pop()
    path = "df-data-science-test-pipelines/out/364866568815/1982582192601038848/train_-7242054282625679360/model"
    myobj = {'message': {'model_path': path}}
    print(url, myobj)
    x = requests.post(url, json = myobj)
    print(x)
'''


@dsl.pipeline(
    name='training-pipeline',
    description='Learning to make a training pipeline',
    pipeline_root="gs://df-data-science-test-pipelines/out")
def pipeline(
    url: str = "gs://df-data-science-test-data/vt_data.csv"
):
    data_op = get_dataset(url)

    train_op = (train(
            train_ds=data_op.outputs["train_ds"],
        ).
        set_cpu_limit('4').
        set_memory_limit('64G').
        add_node_selector_constraint('cloud.google.com/gke-accelerator', 'NVIDIA_TESLA_T4').
        set_gpu_limit('1'))

    evaluate_op = evaluate(
        data_op.outputs["test_ds"],
        train_op.outputs["model"])

    with dsl.Condition(evaluate_op.outputs["deploy"] == "true", name="deploy"):
        serve(train_op.outputs["model"])


compiler.Compiler().compile(pipeline_func=pipeline, package_path='pipeline.json')
