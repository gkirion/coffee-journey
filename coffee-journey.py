from flask import Flask, flash, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS, cross_origin
from flask_api import status
from bson import json_util, Decimal128
from bson.objectid import ObjectId
from bson.json_util import dumps, loads 
import pymongo
from flask.json import jsonify
import logging
import requests
import time
from flask.wrappers import Response
from InvalidDataError import InvalidDataError
from decimal import *

app = Flask(__name__)
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'
app.config['IMAGESERV_URL'] = 'http://localhost:6000/imageserv/'
app.config['IMAGE_STORE'] = 'images/'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
mongo_client = pymongo.MongoClient("mongodb://localhost:27017")
database = mongo_client['coffee-journey']
coffee_collection = database['coffees']
logging.basicConfig(level = logging.DEBUG)
logger = logging.getLogger(__name__)

@app.route('/coffeeJourney/', methods=['POST'])
@cross_origin()
def add_coffee():
    try:
        name = request.form['name'].strip()
        company = request.form['company'].strip()
        tags = request.form['tags'].strip()
        coffee = {'name': name, 'company': company, 'tags': tags}
        if 'price' in request.form:
            price = request.form['price'].strip()
            if not is_price_valid(price):
                return {'result': 'invalid price'}, status.HTTP_400_BAD_REQUEST
            if (len(price) > 0):
                price = Decimal128(price)
                coffee['price'] = price
        
        start = time.perf_counter()
        coffee = coffee_collection.insert_one(coffee)
        end = time.perf_counter()
        logger.info("coffee insertion time: {:.2f} ms".format((end - start) * 1000))
        coffee_id = str(coffee.inserted_id)
        if len(request.files) > 0:
            file = list(request.files.values())[0]
            logger.info(file)
            # send to imageserv
            start = time.perf_counter()
            file.save(app.config['IMAGE_STORE'] + coffee_id)
            end = time.perf_counter()
            logger.info("image save time: {:.2f} ms".format((end - start) * 1000))
            #logger.info("sending image to imageserv")
            #start = time.perf_counter()
            #response = requests.put('http://127.0.0.1:5001/imageserv/{}'.format(coffee_id), headers={'Connection': 'close'}, files={'image': (file.filename, file, file.content_type)})
            #end = time.perf_counter()
            #logger.info("imageserv response: {}".format(response.text))
            #logger.info("image save time: {:.2f} ms".format((end - start) * 1000))

        start = time.perf_counter()
        coffee_collection.update({'_id': ObjectId(coffee_id)}, {"$set": {'imageUrl': app.config['IMAGESERV_URL'] + coffee_id}})
        end = time.perf_counter()
        logger.info("coffee update time: {:.2f} ms".format((end - start) * 1000))
        logger.info('inserted new coffee with id {}'.format(coffee_id))
        return {'result': 'ok', 'id': coffee_id}
    except KeyError:
        logger.error('missing params')
        return {'result': 'missing params'}, status.HTTP_400_BAD_REQUEST


def is_price_valid(price):
    try:
        price_tokens = price.split('.')
        if len(price_tokens) == 2:
            decimal = price_tokens[1]
            if len(decimal) > 2:
                raise InvalidDataError('invalid price')
        if len(price) > 0:
            price = Decimal(price)
        return True
    except InvalidDataError as invalid_data_error:
        logger.error(str(invalid_data_error))
        return False
    except InvalidOperation:
        logger.error('invalid price')
        return False

def coffee_to_json(coffee):
    coffee_json = {}
    for attr in coffee:
        if attr == '_id':
            coffee_json['id'] = str(coffee['_id'])
        elif attr == 'price':
            coffee_json[attr] = str(coffee[attr])
        else:
            coffee_json[attr] = coffee[attr]
    return coffee_json

@app.route('/coffeeJourney/', methods=['GET'])
@cross_origin()
def get_coffees():
    coffees = list(coffee_collection.find())
    coffees = list(map(coffee_to_json, coffees))
    return Response(dumps(coffees), mimetype='application/json')


@app.route('/coffeeJourney/<coffee_id>', methods=['GET'])
@cross_origin()
def get_coffee(coffee_id):
    if not ObjectId.is_valid(coffee_id):
        return {'result': 'invalid id'}, status.HTTP_400_BAD_REQUEST
    coffees = list(coffee_collection.find({'_id': ObjectId(coffee_id)}))
    if len(coffees) == 0:
        return {'result': 'coffee not found'}, status.HTTP_404_NOT_FOUND
    coffees = list(map(coffee_to_json, coffees))
    return {'result': 'ok', 'coffee': coffees[0]}


@app.route('/coffeeJourney/<coffee_id>', methods=['PUT'])
@cross_origin()
def update_coffee(coffee_id):
    try:
        if not ObjectId.is_valid(coffee_id):
            return {'result': 'invalid id'}, status.HTTP_400_BAD_REQUEST
        name = request.form['name']
        company = request.form['company']
        tags = request.form['tags']
        coffee = {'name': name, 'company': company, 'tags': tags}
        if 'price' in request.form:
            price = request.form['price'].strip()
            if not is_price_valid(price):
                return {'result': 'invalid price'}, status.HTTP_400_BAD_REQUEST
            if (len(price) > 0):
                price = Decimal128(price)
                coffee['price'] = price

        start = time.perf_counter()
        updated_coffee = coffee_collection.update_one({'_id': ObjectId(coffee_id)}, {"$set": coffee})
        end = time.perf_counter()
        if updated_coffee.matched_count == 0:
            logger.info('coffee not found')
            return {'result': 'coffee not found'}, status.HTTP_404_NOT_FOUND
        logger.info("coffee update time: {:.2f} ms".format((end - start) * 1000))
        if len(request.files) > 0:
            file = list(request.files.values())[0]
            logger.info(file)
            # send to imageserv
            start = time.perf_counter()
            file.save(app.config['IMAGE_STORE'] + coffee_id)
            end = time.perf_counter()
            logger.info("image save time: {:.2f} ms".format((end - start) * 1000))

        logger.info('updated coffee with id {}'.format(coffee_id))
        return {'result': 'ok'}
    except KeyError:
        logger.info('missing params')
        return {'result': 'missing params'}, status.HTTP_400_BAD_REQUEST


@app.route('/coffeeJourney/<coffee_id>', methods=['DELETE'])
@cross_origin()
def delete_coffee(coffee_id):
    if not ObjectId.is_valid(coffee_id):
         return {'result': 'invalid id'}, status.HTTP_400_BAD_REQUEST
    coffee = coffee_collection.delete_one({'_id': ObjectId(coffee_id)})
    if coffee.deleted_count == 0:
        return {'result': 'coffee not found'}, status.HTTP_404_NOT_FOUND
    return {'result': 'deleted'}  

@app.route('/coffeeJourney/images/<coffee_id>', methods=['GET'])
@cross_origin()
def get_image(coffee_id):
    if not ObjectId.is_valid(coffee_id):
        return {'result': 'invalid id'}, status.HTTP_400_BAD_REQUEST
    return send_from_directory(app.config['IMAGE_STORE'], coffee_id)