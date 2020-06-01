# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import random
import uuid
import datetime

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request

from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.OntoNamespaces import ACL
from AgentUtil.Agent import Agent
import requests

import logging
logging.basicConfig(level=logging.DEBUG)

import Constants.Constants as Constants

# Configuration stuff
hostname = '127.0.1.1'
port = 9020

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

Valorador = Agent('Valorador',
                       agn.Valorador,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion
    """
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'Pedir_Feedback':
        return pedir_feedback(req, content)
    elif accion == 'Enviar_Feedback':
        return enviar_feedback(req, content)

def pedir_feedback(req, content):
    logging.info("Pedimos feedback")
    id_usuario = req.value(subject=content, predicate=agn['id_usuario'])
    logging.info("ID Usuario = " + str(id_usuario))
    prod = Graph()
    prod = get_prod_usuario(id_usuario)
    return prod

def get_prod_usuario(id_usuario):
    historial_compras = Graph().parse('./data/historial_compras.owl')
    logging.info("ID Usuario en la busqueda " + id_usuario)
    sparql_query = Template('''
        SELECT DISTINCT ?compra ?product ?id ?id_usuario
        WHERE {
            ?compra rdf:type ?type_prod .
            ?compra ns:product ?product .
            ?compra ns:id_usuario ?id_usuario .
            ?compra ns:id ?id .
            FILTER (
                ?id_usuario = '$id_usuario'
            )
        }
    ''').substitute(dict(
        id_usuario = id_usuario
    ))
    result = historial_compras.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            ns=agn,
    ))
    i = 0
    result_message = Graph()
    for x in result:
        producto = agn[x.product + '_' + i]
        logging.info(x.product)
        result_message.add((producto, RDF.type, agn.product))
        result_message.add((producto, agn.nombre, x.product))
        i = i + 1
    return result_message.serialize(format='xml')

def enviar_feedback(req, content):
    logging.info("Guardamos feedback")
    productos = Graph().parse('./data/product.owl')

    for producto in req.subjects(RDF.type, agn.product):
        nombre = req.value(subject=producto, predicate=agn.nombre)
        logging.info(nombre)
        valoracion = req.value(subject=producto, predicate=agn.valoracion)
        logging.info(valoracion)

    for producto in req.subjects(RDF.type, agn.product):
        nombre = req.value(subject=producto, predicate=agn.nombre)
        valoracion = req.value(subject=producto, predicate=agn.valoracion)
        sparql_query = Template('''
            SELECT DISTINCT ?product ?tieneMarca ?peso ?precio ?numeroValoraciones ?valoracionTotal ?tienda ?nombre ?type_product
            WHERE {
                ?product rdf:type ?type_product .
                ?product pontp:tieneMarca ?tieneMarca .
                ?product pontp:peso ?peso .
                ?product pontp:precio ?precio .
                ?product pontp:numeroValoraciones ?numeroValoraciones .
                ?product pontp:valoracionTotal ?valoracionTotal .
                ?product pontp:tienda ?tienda .
                ?product pontp:nombre ?nombre .
                FILTER (
                    ?nombre = '$nombre'
                )
            }
        ''').substitute(dict(
            nombre=nombre       
        ))
        result = productos.query(
            sparql_query,
            initNs=dict(
                rdf=RDF,
                ns=agn,
                pontp=Namespace("http://www.products.org/ontology/property/")
            )
        )
        pontp=Namespace("http://www.products.org/ontology/property/")
        for compra in result:
            logging.info(str(compra.nombre))
            logging.info(str(compra.peso))
            logging.info(str(compra.tienda))
            logging.info(str(compra.type_product))
            productos.remove((compra, pontp.numeroValoraciones, None))
            compra.numeroValoraciones = Literal(compra.numeroValoraciones + 1)
            logging.info(compra.numeroValoraciones)
            productos.add((compra, pontp.numeroValoraciones, Literal(compra.numeroValoraciones)))

    result_message = Graph()
    return result_message.serialize(format='xml')
    
@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    Valorador.register_agent(DirectoryAgent)
    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')


