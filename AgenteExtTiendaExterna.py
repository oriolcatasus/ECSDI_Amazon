# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import uuid

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request, render_template

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
port = 9010

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgenteExtTiendaExterna = Agent('AgenteExtTiendaExterna',
                       agn.AgenteExtTiendaExterna,
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


@app.route("/", methods=['GET', 'POST'])
def comunicacion():
    if request.method == 'GET':
        return render_template('vendedor_externo.html')

    global mss_cnt
  
    message = Graph()
    mss_cnt = mss_cnt + 1
    peticion = agn['enviar_peticion_' + str(mss_cnt)]
    message.add((peticion, RDF.type, Literal('Enviar_Peticion')))
    if request.form['nombre_tienda']:
        message.add((peticion, agn.nombre_tienda, Literal((request.form['nombre_tienda']))))
    if request.form['nombre_producto']:
        message.add((peticion, agn.nombre, Literal((request.form['nombre_producto']))))
    if request.form['precio_producto']:
        message.add((peticion, agn.precio, Literal(int(request.form['precio_producto']))))
    if request.form['peso_producto']:
        message.add((peticion, agn.peso, Literal(int(request.form['peso_producto']))))
    if request.form['marca']:
        message.add((peticion, agn.tieneMarca, Literal(request.form['marca'].lower())))
    if request.form['tipo']:
        message.add((peticion, agn.tipo, Literal(request.form['tipo'].lower())))
    if request.form['cuenta_bancaria']:
        message.add((peticion, agn.cuenta_bancaria, Literal(int(request.form['cuenta_bancaria']))))    
    comunicadorExterno = AgenteExtTiendaExterna.directory_search(DirectoryAgent, agn.ComunicadorExterno)    
    msg = build_message(
        message,
        perf=Literal('request'),
        sender=AgenteExtTiendaExterna.uri,
        receiver=comunicadorExterno.uri,
        msgcnt=mss_cnt,
        content=peticion
    )
    logging.info("Arriba")
    response = send_message(msg, comunicadorExterno.address)
    for item in response.subjects(RDF.type, Literal('RespuestaPeticion')):
        for RespuestaPeticion in response.objects(item, agn.respuesta_peticion):
            respuesta_peticion= str(RespuestaPeticion)
            logging.info(respuesta_peticion)
    return render_template('vendedor_externo.html')





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
    AgenteExtTiendaExterna.register_agent(DirectoryAgent)
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