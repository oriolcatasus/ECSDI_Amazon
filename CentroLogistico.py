# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import uuid

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
port = 9003

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

CentroLogistico = Agent('CentroLogistico',
                       agn.CentroLogistico,
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
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'Empezar_Envio_Compra':        
        return empezar_envio_compra(req, content)


def empezar_envio_compra(req, content):
    codigo_postal = str(req.value(subject=content, predicate=agn.codigo_postal))
    logging.info('codigo postal: ' + codigo_postal)
    direccion = str(req.value(subject=content, predicate=agn.direccion))
    logging.info('direccion: ' + direccion)
    for item in req.subjects(RDF.type, agn.product):
        nombre=str(req.value(subject=item, predicate=agn.nombre))
        logging.info(nombre)

    lotes_graph = Graph()
    try:
        lotes_graph.parse('./data/lotes.owl')
    except Exception as e:
        logging.info('No lotes graph found')
        cp = agn['codigo_postal']
        lotes_graph.add((cp, RDF.type, Literal('Codigo_Postal')))
    add_products_to_lote(req, lotes_graph, codigo_postal)
    logging.info(codigo_postal)
    sparql_query = Template('''
        SELECT (COUNT(*) as ?cnt)?producto ?codigo_postal
        WHERE {
            ?producto rdf:type ?type_prod .
            ?producto ns:codigo_postal ?codigo_postal .
            FILTER (
                ?codigo_postal = '$codigo_postal'
            )
        }
    ''').substitute(dict(
        codigo_postal=codigo_postal       
    ))
    result = lotes_graph.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            ns=agn
        )
    )
    logging.info('Result:')
    for x in result:
        logging.info(x.cnt)

    lotes_graph.serialize('./data/lotes.owl')
    return Graph().serialize(format='xml')

def add_products_to_lote(req, lotes_graph, codigo_postal):
    for item in req.subjects(RDF.type, agn.product):
        nombre=req.value(subject=item, predicate=agn.nombre)
        logging.info(nombre)
        lotes_graph.add((item, RDF.type, agn.product))
        lotes_graph.add((item, agn.nombre, Literal(nombre)))
        lotes_graph.add((item, agn.codigo_postal, Literal(codigo_postal)))




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
    CentroLogistico.register_agent(DirectoryAgent)
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
