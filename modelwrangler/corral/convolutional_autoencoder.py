"""Module sets up Dense Autoencoder model"""

import tensorflow as tf

from modelwrangler.model_wrangler import ModelWrangler
import modelwrangler.tf_ops as tops
from modelwrangler.tf_models import BaseNetworkParams, BaseNetwork, ConvLayerConfig, LayerConfig

class ConvolutionalAutoencoderParams(BaseNetworkParams):
    """Dense autoencoder params
    """

    LAYER_PARAM_TYPES = {
        "encode_params": ConvLayerConfig,
        "bottleneck_params": ConvLayerConfig,
        "decode_params": ConvLayerConfig,
        "output_params": ConvLayerConfig
    }

    MODEL_SPECIFIC_ATTRIBUTES = {
        "name": "conv_autoenc",
        "in_size": 40,
        "encode_nodes": [10],
        "encode_params": {
            "dropout_rate": 0.1,
            "kernel": 5,
            "strides": 1,
            "pool_size": 2
        },
        "bottleneck_dim": 3,
        "bottleneck_params": {
            "dropout_rate": None,
            "kernel": 5,
            "strides": 1,
            "pool_size": 1
        },
        "decode_nodes": [10],
        "decode_params": {
            "dropout_rate": None,
            "kernel": 5,
            "strides": 1,
            "pool_size": 2
        },
        "output_params": {
            "dropout_rate": None,
            "activation": None,
            "act_reg": None,
            "kernel": 1,
            "strides": 1,
            "pool_size": 1
        },
    }


class ConvolutionalAutoencoderModel(BaseNetwork):
    """Dense autoencoder model
    """

    # pylint: disable=too-many-instance-attributes

    PARAM_CLASS = ConvolutionalAutoencoderParams

    def setup_layers(self, params):
        """Build all the model layers
        """

        # Input and encoding layers
        in_shape = [None]
        if isinstance(params.in_size, (list, tuple)):
            in_shape.extend(params.in_size)
        else:
            in_shape.extend([params.in_size, 1])

        encode_layers = [
            tf.placeholder(
                "float",
                name="input",
                shape=in_shape
                )
        ]

        for idx, num_nodes in enumerate(params.encode_nodes):
            encode_layers.append(
                self.make_conv_layer(
                    encode_layers[-1],
                    num_nodes,
                    'encode_{}'.format(idx),
                    params.encode_params
                    )
            )

        # Bottleneck and decoding layers
        decode_layers = [
            self.make_conv_layer(
                encode_layers[-1],
                params.bottleneck_dim,
                'bottleneck',
                params.bottleneck_params
                )
        ]

        for idx, num_nodes in enumerate(params.decode_nodes):
            decode_layers.append(
                self.make_deconv_layer(
                    decode_layers[-1],
                    num_nodes,
                    'decode_{}'.format(idx),
                    params.decode_params
                    )
            )

        # Standardizing the input/output layer names
        in_layer = encode_layers[0]

        target_layer = tf.placeholder(
            "float",
            name="target",
            shape=in_layer.get_shape().as_list()
        )

        out_layer = tops.fit_to_shape(
            self.make_deconv_layer(
                decode_layers[-1],
                1,
                'output_layer',
                params.output_params
            ),
            target_layer.get_shape().as_list()
        )

        loss = tops.loss_mse(
            target_layer,
            out_layer
        )

        return in_layer, out_layer, target_layer, loss


class ConvolutionalAutoencoder(ModelWrangler):
    """Convolutional Autoencoder
    """
    def __init__(self, in_size=10, **kwargs):
        super(ConvolutionalAutoencoder, self).__init__(
            model_class=ConvolutionalAutoencoderModel,
            in_size=in_size,
            **kwargs)
