# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
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
port = 9001

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgentExtUser = Agent('AgentExtUser',
                       agn.AgentExtUser,
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
    global dsgraph
    global mss_cnt


    message = Graph()
    mss_cnt = mss_cnt + 1
    search = agn['search_query_' + str(mss_cnt)]
    message.add((search, agn['Precio'], Literal('200')))
    #message.add((search, RDF.type, Literal(OntologyConstants.ACTION_SEARCH_PRODUCTS)))
    message.add((search, RDF.type, Literal('Buscar_Productos')))
    AtencionAlCliente = AgentExtUser.directory_search(DirectoryAgent, agn.AtencionAlCliente)
    logging.info('Nom:')
    logging.info(AtencionAlCliente.name)
    msg = build_message(
        message,
        perf=Literal('request'),
        sender=AgentExtUser.uri,
        receiver=AtencionAlCliente.uri,
        msgcnt=mss_cnt,
        content=search
    )
    response = send_message(msg, AtencionAlCliente.address)
    #content = get_message_properties(response)['prod']
    for item in response.subjects(RDF.type, agn.product):
        product_name=str(response.value(subject=item, predicate=agn.product_name))
        logging.info('Response name:')
        logging.info(product_name)

    pass


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
    AgentExtUser.register_agent(DirectoryAgent)
    comunicacion()
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


