import os
import sys
import json
from typing import List
from flask import Flask, render_template, request
from flask_restful import reqparse, Api, Resource
from src.models_evaluation.sentiment_analysis_tfidf import DumbModel
from src.models_evaluation.sentiment_analysis_rnn import RNNModel as SARNN
from src.models_evaluation.sentiment_analysis_rnn import DataPreprocessor as SAPreprocessor
from src.models_evaluation.named_entity_recognition_rnn import RNNModel as NERRNN
from src.models_evaluation.named_entity_recognition_rnn import DataPreprocessor as NERPreprocessor


app = Flask(__name__)
api = Api(app)
global_model_config = list()


parser = reqparse.RequestParser()
parser.add_argument('query')


# sentiment analysis callers
class PredictSentiment(Resource):
    """
    utility class for the api_resource method
    """
    def __init__(self, model, pre_processor):
        self.model = model
        self.pre_processor = pre_processor

    def get_from_service(self, input_list: List[str]):
        """
        gets the user's query strings.
        The query could either be a single string or a list of multiple strings
        Return:
            dictionary containing probilities prediction as value sorted by each string as key
        """
        if self.model.model_name == "rnn":
            query_list = SAPreprocessor.preprocess_data(input_list, self.pre_processor)
        probs = self.model.predict_proba(query_list)
        return probs

    def get(self):
        """
        Gets the user's query strings.
        The query could either be a single string or a list of multiple strings
        Return:
            dictionary containing probilities prediction as value sorted by each string as key
        """
        # use parser and find the user's query
        args = parser.parse_args()
        query_list = args['query']
        if self.model.model_name == "rnn":
            query_list = SAPreprocessor.preprocess_data(query_list, self.pre_processor)
        probs = self.model.predict_proba(query_list)
        return self.model.get_output(probs, query_list)


@app.route('/sentimentAnalysis', methods=['POST', 'GET'])
def sentiment_analysis():
    """
    sentiment analysis service function
    """
    if request.method == 'POST':
        task_content = request.form['content']
        new_prediction = PredictSentiment(model=global_model_config[0], pre_processor=global_model_config[1])
        output = new_prediction.get_from_service([task_content])
        return json.dumps(output[0] * 100)
    #     return render_template('sentiment_analysis.html', output=int(output[0] * 100))
    # else:
    #     return render_template('sentiment_analysis.html')


# Named entity recognition callers
class PredictEntities(Resource):
    """
    utility class for the api_resource method
    """
    def __init__(self, model, pre_processor):
        self.model = model
        self.pre_processor = pre_processor

    def get_from_service(self, input_list: List[str]):
        """
        gets the user's query strings.
        The query could either be a single string or a list of multiple strings
        Return:
            dictionary containing probilities prediction as value sorted by each string as key
        """
        questions_list_encoded, questions_list_tokenized, n_tokens =\
            NERPreprocessor.preprocess_data(input_list, self.pre_processor)
        preds = self.model.predict(questions_list_encoded, self.pre_processor["labels_to_idx"], n_tokens)
        display_result = self.model.visualize(questions_list_tokenized, preds)
        return display_result

    def get(self):
        """
        gets the user's query strings.
        The query could either be a single string or a list of multiple strings
        Return:
            dictionary containing probilities prediction as value sorted by each string as key
        """
        # use parser and find the user's query
        args = parser.parse_args()
        query_list = args['query'].strip('][').split(',')
        print("query list")
        print(args['query'])
        questions_list_encoded, questions_list_tokenized, n_tokens =\
            NERPreprocessor.preprocess_data(query_list, self.pre_processor)
        preds = self.model.predict(questions_list_encoded, self.pre_processor["labels_to_idx"], n_tokens)
        display_result = self.model.visualize(questions_list_tokenized, preds)
        return display_result


@app.route('/namedEntityRecognition', methods=['POST', 'GET'])
def named_entity_recognition():
    """
    named entity recognition service function
    """
    if request.method == 'POST':
        task_content = request.form['content']
        new_prediction = PredictEntities(model=global_model_config[2], pre_processor=global_model_config[3])
        output = new_prediction.get_from_service([task_content])
        return json.dumps(output)


@app.route('/', methods=['POST', 'GET'])
def index():
    """
    index function
    """
    return render_template('index.html')


def main():
    """ if boolean is true bring the application up"""
    app_up = len(sys.argv) < 2

    model_to_evaluate = "rnn"
    sentiment_analysis_pre_processor = None
    sentiment_analysis_model = None
    if model_to_evaluate == "tfidf":
        sentiment_analysis_model = DumbModel.load_model()
    elif model_to_evaluate == "rnn":
        sentiment_analysis_model, preprocessor_file = SARNN.load_model()
    if sentiment_analysis_model is None or preprocessor_file is None:
        raise ValueError("there is no corresponding model file")
    if model_to_evaluate == "rnn":
        sentiment_analysis_pre_processor = SAPreprocessor.load_preprocessor(preprocessor_file)

    ner_model, preprocessor_file = NERRNN.load_model()
    ner_pre_processor = NERPreprocessor.load_preprocessor(preprocessor_file)
    if ner_model is None or ner_pre_processor is None:
        raise ValueError("there is no corresponding model file")

    global_model_config.extend([sentiment_analysis_model, sentiment_analysis_pre_processor,
                                ner_model, ner_pre_processor])
    if app_up:
        # the PredictSentiment methode will be executed in the sentimentAnalysis() method
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port, threaded=False)
    else:
        print(PredictSentiment(sentiment_analysis_model, sentiment_analysis_pre_processor))
        print(PredictEntities(ner_model, ner_pre_processor))


if __name__ == '__main__':
    main()