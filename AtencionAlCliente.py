# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket

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
port = 9002

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AtencionAlCliente = Agent('AtencionAlCliente',
                       agn.AtencionAlCliente,
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
    logging.info('Content:')
    logging.info(content)
    
    req_dict = {}
    if req.value(subject=content, predicate=agn['min_precio']):
        logging.info('Entra MIN precio')
        req_dict['min_precio'] = req.value(subject=content, predicate=agn['min_precio'])
        logging.info(req_dict['min_precio'])
    
    if req.value(subject=content, predicate=agn['max_precio']):
        logging.info('Entra MAX precio')
        req_dict['max_precio'] = req.value(subject=content, predicate=agn['max_precio'])
        logging.info(req_dict['max_precio'])   


    '''
        RESPUESTA
    '''
    productos = Graph()
    productos.parse('./data/product.owl')

    sparql_query = Template('''
        SELECT DISTINCT ?producto ?nombre ?precio ?peso ?tieneMarca
        WHERE {
            ?producto rdf:type ?type_prod .
            ?producto pontp:nombre ?nombre .
            ?producto pontp:precio ?precio .
            ?producto pontp:peso ?peso .
            ?producto pontp:tieneMarca ?tieneMarca .
            FILTER (
                ?precio > $min_precio && 
                ?precio < $max_precio
            )
        }
    ''').substitute(dict(
        min_precio=req_dict['min_precio'],
        max_precio=req_dict['max_precio']
    ))

    result = productos.query(
        sparql_query,
        initNs=dict(
            foaf=FOAF,
            rdf=RDF,
            ns=agn,
            pontp=Namespace("http://www.products.org/ontology/property/")
        )
    )

    result_message = Graph()
    for x in result:
        result_message.add((x.producto, RDF.type, agn.product))
        result_message.add((x.producto, agn.nombre, x.nombre))
        result_message.add((x.producto, agn.peso, x.peso))
        result_message.add((x.producto, agn.precio, x.precio))
        result_message.add((x.producto, agn.tieneMarca, x.tieneMarca))

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
    AtencionAlCliente.register_agent(DirectoryAgent)
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


