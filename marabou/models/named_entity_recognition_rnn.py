import os
import string
import pickle
import re
from itertools import compress
from typing import List
import matplotlib.pyplot as plt
import numpy as np
from nltk.tokenize import word_tokenize
from sklearn.model_selection import train_test_split
from tensorflow.keras import Model
from tensorflow.keras.utils import to_categorical
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.models import load_model
from tensorflow.keras.layers import Embedding, Dense, LSTM, Input, TimeDistributed, Bidirectional, Dropout
from marabou.utils.config_loader import NamedEntityRecognitionConfigReader
from marabou.models.embedding_layers import FastTextEmbedding, Glove6BEmbedding, ElmoEmbedding


class DataPreprocessor:
    """
    Utility class performing several data preprocessing steps
    """
    def __init__(self, max_sequence_length: int, validation_split: float, vocab_size: int):
        self.max_sequence_length = max_sequence_length
        self.validation_split = validation_split
        self.vocab_size = vocab_size
        self.tokenizer_obj = None
        self.labels_to_idx = None

    def clean_data(self, X: List):
        """
        performs data cleaning operations such as removing html breaks, lower case,
        remove stopwords ...
        :param X: input reviews to be cleaned
        :return: None
        """
        print("===========> data cleaning")
        review_lines = list()
        for line in X:
            tokens = [w.lower() for w in line]
            table = str.maketrans('', '', string.punctuation)
            stripped = [w.translate(table) for w in tokens]
            words = [word for word in stripped if word.isalpha()]
            # stop_words = set(stopwords.words('english'))
            # words = [word for word in words if word not in stop_words]
            review_lines.append(words)
        print("----> data cleaning finish")
        return review_lines

    def tokenize_text(self, X: List, y: List):
        """
        performs data tokenization into a format that is digestible by the model
        :param X: list of predictors already cleaned
        :return: tokenizer object and tokenized input features
        """
        print("===========> data tokenization")
        # features tokenization
        self.tokenizer_obj = Tokenizer(num_words=self.vocab_size)
        self.tokenizer_obj.fit_on_texts(X)
        sequences = self.tokenizer_obj.texts_to_sequences(X)
        word_index = self.tokenizer_obj.word_index
        review_pad = pad_sequences(sequences, maxlen=self.max_sequence_length, padding="post",
                                   value=self.vocab_size - 1)
        # labels tokenization
        flat_list = [item for sublist in y for item in sublist]
        unique_labels = list(set(flat_list))
        self.labels_to_idx = {t: i for i, t in enumerate(unique_labels)}
        tokenized_labels = [[self.labels_to_idx[word] for word in sublist] for sublist in y]
        tokenized_labels = pad_sequences(tokenized_labels, maxlen=self.max_sequence_length, padding="post",
                                         value=self.labels_to_idx["O"])
        print("----> data tokenization finish")
        print("found %i unique tokens" % len(word_index))
        print("features tensor shape ", review_pad.shape)
        print("labels tensor shape ", tokenized_labels.shape)
        return review_pad, tokenized_labels

    def split_train_test(self, X, y):
        """
        wrapper method to split training data into a validation set and a training set
        :param X: tokenized predictors
        :param y: labels
        :return: a tuple consisting of training predictors, training labels, validation predictors, validation labels
        """
        print("===========> data split")
        y = [to_categorical(i, num_classes=len(self.labels_to_idx)) for i in y]
        X_train, X_test, y_train, y_test = train_test_split(X, y, shuffle=True, test_size=self.validation_split)
        print("----> data split finish")
        print('training features shape ', X_train.shape)
        print('testing features shape ', X_test.shape)
        print('training target shape ', np.asarray(y_train).shape)
        print('testing target shape ', np.asarray(y_test).shape)
        return X_train, X_test, np.asarray(y_train), np.asarray(y_test)

    def save_preprocessor(self, file_name_prefix):
        """
        stores the data preprocessor under 'models folder'
        :param file_name_prefix: a file name prefix having the following format 'sentiment_analysis_%Y%m%d_%H%M%S'
        :return: None
        """
        model_folder = os.path.join(os.getcwd(), "models")
        if not os.path.isdir(model_folder):
            os.mkdir(model_folder)
        file_url = os.path.join(model_folder, file_name_prefix + "_preprocessor.pkl")
        with open(file_url, 'wb') as handle:
            pickle.dump(self.tokenizer_obj, handle, protocol=pickle.HIGHEST_PROTOCOL)
            pickle.dump(self.max_sequence_length, handle, protocol=pickle.HIGHEST_PROTOCOL)
            pickle.dump(self.vocab_size, handle, protocol=pickle.HIGHEST_PROTOCOL)
            pickle.dump(self.labels_to_idx, handle, protocol=pickle.HIGHEST_PROTOCOL)
        print("----> proprocessor object saved to %s" % file_url)

    @staticmethod
    def load_preprocessor(preprocessor_file_name):
        """
        loads preprocessing tools for the model
        :param preprocessor_file_name: data to evaluate
        :return: preprocessed object
        """
        preprocessor = {}
        preprocessor_file_name = os.path.join(os.getcwd(), "models", preprocessor_file_name)
        with open(preprocessor_file_name, 'rb') as f:
            preprocessor['tokenizer_obj'] = pickle.load(f)
            preprocessor['max_sequence_length'] = pickle.load(f)
            preprocessor['vocab_size'] = pickle.load(f)
            preprocessor['labels_to_idx'] = pickle.load(f)
        return preprocessor

    @staticmethod
    def preprocess_data(data, preprocessor):
        """
        performs data preprocessing before inference
        :param data: data to evaluate
        :param preprocessor: tokenizer object
        :return: preprocessed data
        """
        lines = list()
        n_tokens_list = list()
        for line in data:
            if not isinstance(line, list):
                line = word_tokenize(line)
            tokens = [w.lower() for w in line]
            table = str.maketrans('', '', string.punctuation)
            stripped = [w.translate(table) for w in tokens]
            words = [word for word in stripped if word.isalpha()]
            lines.append(words)
            n_tokens_list.append(len(words))
        data = preprocessor['tokenizer_obj'].texts_to_sequences(lines)
        data = pad_sequences(data, maxlen=preprocessor['max_sequence_length'], padding="post",
                             value=preprocessor['vocab_size'] - 1)
        return data, n_tokens_list


class RNNModel:
    """
    Handles the RNN model
    """
    def __init__(self, **kwargs):
        self.model_name = "rnn"
        self.use_pretrained_embedding = None
        self.vocab_size = None
        self.embedding_dimension = None
        self.embeddings_path = None
        self.max_length = None
        self.word_index = None
        self.embedding_layer = None
        self.model = None
        self.n_labels = None
        self.n_iter = 10
        keys = kwargs.keys()
        if 'config' in keys and 'data_preprocessor' in keys:
            self.init_from_config_file(kwargs['config'], kwargs['data_preprocessor'])
        else:
            self.init_from_files(kwargs['h5_file'], kwargs['class_file'])

    def init_from_files(self, h5_file, class_file):
        """
        initialize the class from a previously saved model
        :param h5_file: url to a saved class
        :return: None
        """
        self.model = load_model(h5_file)
        with open(class_file, 'rb') as f:
            self.use_pretrained_embedding = pickle.load(f)
            self.vocab_size = pickle.load(f)
            self.embedding_dimension = pickle.load(f)
            self.embeddings_path = pickle.load(f)
            self.max_length = pickle.load(f)
            self.word_index = pickle.load(f)

    def init_from_config_file(self, config: NamedEntityRecognitionConfigReader, data_preprocessor: DataPreprocessor):
        """
        initialize the class for the first time from a given configuration file and data processor
        :param config: .json configuration reader
        :param data_preprocessor: preprocessing tool for the training data
        :return: None
        """
        self.use_pretrained_embedding = config.pre_trained_embedding
        self.vocab_size = config.vocab_size
        self.embedding_dimension = config.embedding_dimension
        self.embeddings_name = config.embedding_algorithm
        if self.embeddings_name == "glove":
            self.embeddings_path = config.embeddings_path_glove
        elif self.embeddings_name == "fasttext":
            self.embeddings_path = config.embeddings_path_fasttext
        if config.experimental_mode:
            self.n_iter = 10
        self.max_length = config.max_sequence_length
        self.n_labels = len(data_preprocessor.labels_to_idx)
        self.word_index = data_preprocessor.tokenizer_obj.word_index
        self.embedding_layer = self.build_embedding()
        self.model = self.build_model()

    def build_embedding(self):
        """
        builds the embedding layer. depending on the configuration, it will either
        load a pretrained embedding or create an empty embedding to be trained along
        with the data
        :return: None
        """
        if self.use_pretrained_embedding and self.embeddings_name == "glove":
            glove_embeddings = Glove6BEmbedding(self.embedding_dimension, self.word_index,
                                                self.vocab_size, self.embeddings_path, self.max_length)
            embedding_layer = glove_embeddings.embedding_layer
        elif self.use_pretrained_embedding and self.embeddings_name == "elmo":
            embedding_layer = ElmoEmbedding(self.use_pretrained_embedding, 1024)
        elif self.use_pretrained_embedding and self.embeddings_name == "fasttext":
            fasttext_embeddings = FastTextEmbedding(self.word_index, self.vocab_size, self.embeddings_path,
                                                    self.max_length)
            embedding_layer = fasttext_embeddings.embedding_layer
        else:
            embedding_layer = Embedding(self.vocab_size, self.embedding_dimension, input_length=self.max_length)
        return embedding_layer

    def build_model(self):
        """
        builds an RNN model according to fixed architecture
        :return: None
        """
        print("===========> build model")
        # Run the function
        input_layer = Input(shape=(self.max_length,), name='input')
        x = self.embedding_layer(input_layer)
        x = Dropout(0.1)(x)
        x = Bidirectional(LSTM(units=100, return_sequences=True, recurrent_dropout=0.1))(x)
        x = TimeDistributed(Dense(self.n_labels, activation='softmax'))(x)
        model = Model(inputs=input_layer, outputs=x)
        # non sequential preferred because it can incorporate residual dependencies
        # model = Sequential()
        # model.add(self.embedding_layer)
        # model.add(LSTM(64, dropout=0.2, recurrent_dropout=0.2))
        # model.add(Dense(250, activation='relu'))
        # model.add(Dense(1, activation='sigmoid'))

        model.compile(loss='categorical_crossentropy', optimizer="adam", metrics=['acc'])
        print(model.summary())
        return model

    def fit(self, X_train, y_train, X_test=None, y_test=None):
        """
        fits the model object to the data
        :param X_train: numpy array containing encoded training features
        :param y_train: numpy array containing training targets
        :paran X_test: numpy array containing encoded test features
        :param y_test: numpy array containing test targets
        :return: list of values related to each datasets and loss function
        """
        if (X_test is not None) and (y_test is not None):
            history = self.model.fit(x=X_train, y=y_train, epochs=self.n_iter, batch_size=64,
                                     validation_data=(X_test, y_test), verbose=2)
        else:
            history = self.model.fit(x=X_train, y=y_train, epochs=self.n_iter, batch_size=64, verbose=2)
        return history

    def predict(self, encoded_text_list, n_tokens_list, labels_to_idx):
        """
        inference method
        :param encoded_text_list: a list of texts to be evaluated. the input is assumed to have been
        preprocessed
        :param n_tokens_list: number of tokens in each input string before padding
        :param labels_to_idx: a dictionary containing the conversion from each class label to its id
        :return: a numpy array containing the class for token character in the sentence
        """
        idx_to_labels = {v: k for k, v in labels_to_idx.items()}
        probs = self.model.predict(encoded_text_list)
        labels_list = []
        for i in range(len(probs)):
            real_probs = probs[i][:n_tokens_list[i]]
            classes = np.argmax(real_probs, axis=1)
            labels = [idx_to_labels[cl] for cl in classes]
            labels_list.append(labels)
        return labels_list

    def predict_proba(self, encoded_text_list, n_tokens_list):
        """
        inference method
        :param encoded_text_list: a list of texts to be evaluated. the input is assumed to have been
        preprocessed
        :param n_tokens_list: number of tokens in each input string before padding
        :return: a numpy array containing the probabilities of a positive review for each list entry
        """
        probs = self.model.predict(encoded_text_list)
        real_probs_list = []
        for i in range(len(probs)):
            real_probs = probs[i][:n_tokens_list[i]]
            real_probs_list.append(real_probs)
        return real_probs_list

    def save_model(self, file_name_prefix):
        """
        saves the trained model into a h5 file
        :param file_name_prefix: a file name prefix having the following format 'sentiment_analysis_%Y%m%d_%H%M%S'
        :return: None
        """
        model_folder = os.path.join(os.getcwd(), "models")
        if not os.path.isdir(model_folder):
            os.mkdir(model_folder)
        file_url_keras_model = os.path.join(model_folder, file_name_prefix + "_rnn_model.h5")
        self.model.save(file_url_keras_model)
        file_url_class = os.path.join(model_folder, file_name_prefix + "_rnn_class.pkl")
        with open(file_url_class, 'wb') as handle:
            pickle.dump(self.use_pretrained_embedding, handle)
            pickle.dump(self.vocab_size, handle)
            pickle.dump(self.embedding_dimension, handle)
            pickle.dump(self.embeddings_path, handle)
            pickle.dump(self.max_length, handle)
            pickle.dump(self.word_index, handle)
        print("----> model saved to %s" % file_url_keras_model)
        print("----> class saved to %s" % file_url_class)

    def save_learning_curve(self, history, file_name_prefix):
        """
        saves the learning curve plot
        :param history: a dictionary object containing training and validation dataset loss function values and
        objective function values for each training iteration
        :param file_name_prefix: a file name prefix having the following format 'sentiment_analysis_%Y%m%d_%H%M%S'
        :return: None
        """
        plot_folder = os.path.join(os.getcwd(), "plots")
        if not os.path.isdir(plot_folder):
            os.mkdir(plot_folder)

        acc = history.history['acc']
        val_acc = history.history['val_acc']
        loss = history.history['loss']
        val_loss = history.history['val_loss']
        epochs = range(len(acc))

        fig, ax = plt.subplots(1, 2)
        ax[0].plot(epochs, acc, 'bo', label='Training acc')
        ax[0].plot(epochs, val_acc, 'b', label='Validation acc')
        ax[0].set_title('Training and validation accuracy')
        ax[0].set_ylim([0.6, 1])
        ax[0].legend()
        fig.suptitle('model performance')
        ax[1].plot(epochs, loss, 'bo', label='Training loss')
        ax[1].plot(epochs, val_loss, 'b', label='Validation loss')
        ax[1].set_title('Training and validation loss')
        ax[1].set_ylim([0, 1])
        ax[1].legend()
        plot_file_url = os.path.join(plot_folder, file_name_prefix + "_learning_curve.png")
        plt.savefig(plot_file_url)
        plt.close()
        print("----> learning curve saved to %s" % plot_file_url)

    @staticmethod
    def load_model():
        """
        extracts a model saved using the save_model function
        :return: a model object and a tokenizer object
        """
        trained_model = None
        model_dir = os.path.join(os.getcwd(), "models")
        model_files_list = os.listdir(os.path.join(os.getcwd(), "models"))
        if len(model_files_list) > 0:
            rnn_models_idx = [("named_entity_recognition" in f) and ("rnn" in f) for f in model_files_list]
            if np.sum(rnn_models_idx) > 0:
                rnn_model = list(compress(model_files_list, rnn_models_idx))
                model_dates = [int(''.join(re.findall(r'\d+', f))) for f in rnn_model]
                h5_file_name = rnn_model[np.argmax(model_dates)]
                preprocessor_file = h5_file_name.replace("rnn_model.h5", "preprocessor.pkl")
                class_file = h5_file_name.replace("rnn_model.h5", "rnn_class.pkl")
                if (os.path.isfile(os.path.join(model_dir, preprocessor_file))) and\
                        (os.path.isfile(os.path.join(model_dir, class_file))):
                    trained_model = RNNModel(h5_file=os.path.join(model_dir, h5_file_name),
                                             class_file=os.path.join(model_dir, class_file))
                    return trained_model, preprocessor_file
                return None, None
            return None, None
        return None, None